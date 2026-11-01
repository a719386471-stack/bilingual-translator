import base64,hashlib,json,shutil,socket,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from install_support import NAME,VERSION,read_json,write_json,extension_id
from install_native_host import install
from setup_installer import verify_assets,rollback_runtime
from uninstall import uninstall
from native_host import control
ROOT=Path(__file__).resolve().parents[1]

class InstallationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.data=self.base/'另一个用户 安装数据';self.hosts=self.base/'hosts'
  self.data.mkdir();self.hosts.mkdir();(self.data/'runtime/bin').mkdir(parents=True)
  (self.data/'runtime/bin/python3').symlink_to(sys.executable)
 def tearDown(self):self.tmp.cleanup()
 def test_fixed_id_and_repair_preserve_credentials_and_records(self):
  (self.data/'connection.json').write_text('{"pairing_key":"fixture-private-pairing-value-123456"}')
  (self.data/'cache.sqlite').write_bytes(b'fixture-cache-and-usage')
  first=install(ROOT,self.data,self.hosts,port=19492,start=False)
  key=(ROOT/'packaging/release-public-key.txt').read_text().strip()
  self.assertEqual(first['extensionId'],extension_id(key))
  self.assertEqual(read_json(self.data/'extension/manifest.json')['key'],key)
  second=install(ROOT,self.data,self.hosts,port=19492,start=False)
  self.assertEqual(first['extensionId'],second['extensionId'])
  self.assertEqual(read_json(self.data/'connection.json')['pairing_key'],'fixture-private-pairing-value-123456')
  self.assertEqual((self.data/'cache.sqlite').read_bytes(),b'fixture-cache-and-usage')
  self.assertEqual(read_json(self.hosts/(NAME+'.json'))['allowed_origins'],['chrome-extension://'+first['extensionId']+'/'])
 def test_legacy_identity_is_preserved_on_existing_computer(self):
  write_json(self.data/'service/native-config.json',{'origin':'chrome-extension://'+'a'*32+'/'})
  result=install(ROOT,self.data,self.hosts,start=False)
  self.assertEqual(result['extensionId'],'a'*32)
  self.assertFalse(read_json(self.data/'install-receipt.json')['managed_extension'])
 def test_failed_update_restores_previous_program_and_registration(self):
  install(ROOT,self.data,self.hosts,port=19492,start=False)
  old=(self.data/'service/native-config.json').read_bytes();manifest=(self.hosts/(NAME+'.json')).read_bytes()
  with patch('native_host.control',side_effect=ValueError('fixture startup failure')):
   with self.assertRaises(ValueError):install(ROOT,self.data,self.hosts,port=19493,start=True)
  self.assertEqual((self.data/'service/native-config.json').read_bytes(),old)
  self.assertEqual((self.hosts/(NAME+'.json')).read_bytes(),manifest)
  self.assertEqual(read_json(self.data/'install-receipt.json')['port'],19492)
 def test_assets_corruption_stops_before_install(self):
  root=self.base/'bundle';root.mkdir();(root/'assets').mkdir();(root/'assets/example').write_bytes(b'bad')
  write_json(root/'assets/hashes.json',{'assets/example':hashlib.sha256(b'good').hexdigest()})
  with self.assertRaises(ValueError):verify_assets(root)
 def test_missing_hash_manifest_is_not_silently_accepted(self):
  root=self.base/'broken-bundle';(root/'assets').mkdir(parents=True)
  with self.assertRaisesRegex(ValueError,'清单'):verify_assets(root)
 def test_program_file_changes_are_reported_without_reading_account_files(self):
  install(ROOT,self.data,self.hosts,port=19492,start=False)
  file=self.data/'service/helper.py';file.write_text(file.read_text()+'\n# fixture modification\n')
  report=control('diagnose',self.data)
  self.assertFalse(report['ready']);self.assertEqual(next(c for c in report['checks'] if c['id']=='files')['state'],'error')
 def test_busy_port_is_not_killed_or_replaced(self):
  with socket.socket() as sock:
   sock.bind(('127.0.0.1',0));sock.listen();port=sock.getsockname()[1]
   write_json(self.data/'service/native-config.json',{'port':port})
   with self.assertRaisesRegex(ValueError,'占用'):control('start',self.data)
   self.assertEqual(sock.getsockname()[1],port)
 def test_uninstall_is_recoverable_and_only_moves_owned_manifest(self):
  install(ROOT,self.data,self.hosts,port=19492,start=False)
  (self.data/'connection.json').write_text('{"pairing_key":"fixture-credential-not-to-delete"}')
  (self.data/'cache.sqlite').write_bytes(b'usage-preserved')
  backup=uninstall(self.data,self.hosts,self.base/'recovery')
  self.assertFalse(self.data.exists());self.assertTrue((backup/'NewsBridge/connection.json').exists())
  self.assertEqual((backup/'NewsBridge/cache.sqlite').read_bytes(),b'usage-preserved')
  self.assertTrue((backup/'native-host-manifest.json').exists())
 def test_native_protocol_rejects_other_extensions_and_never_diagnoses_secrets(self):
  result=install(ROOT,self.data,self.hosts,port=19492,start=False)
  write_json(self.data/'connection.json',{'pairing_key':'fixture-private-pairing-value-123456'})
  raw=json.dumps({'action':'connect'}).encode();framed=len(raw).to_bytes(4,'little')+raw
  path=self.data/'service/native_host.py'
  allowed='chrome-extension://'+result['extensionId']+'/'
  rejected=subprocess.run([sys.executable,str(path),'chrome-extension://'+'p'*32+'/'],input=framed,capture_output=True)
  self.assertEqual(rejected.stdout,b'')
  accepted=subprocess.run([sys.executable,str(path),allowed],input=framed,capture_output=True,check=True)
  payload=json.loads(accepted.stdout[4:]);self.assertTrue(payload['ok']);self.assertEqual(payload['data']['pairingKey'],'fixture-private-pairing-value-123456')
  report=control('diagnose',self.data)
  self.assertNotIn('fixture-private',json.dumps(report));self.assertNotIn('pairing_key',json.dumps(report))
 def test_runtime_rollback_restores_previous_interpreter_before_restart(self):
  old=self.data/'runtime.previous';(self.data/'runtime').replace(old)
  new=self.data/'new-runtime';new.mkdir();(self.data/'runtime').symlink_to(new)
  with patch('native_host.control') as restart:
   rollback_runtime(self.data,{'kind':'new','previous':old,'was_running':True})
  self.assertTrue((self.data/'runtime/bin/python3').is_file());self.assertFalse((self.data/'runtime').is_symlink())
  restart.assert_called_once_with('start',self.data)
 def test_other_installation_registration_is_not_overwritten(self):
  write_json(self.hosts/(NAME+'.json'),{'path':'/another-installation/service/native-host'})
  with self.assertRaisesRegex(ValueError,'未覆盖'):install(ROOT,self.data,self.hosts,start=False)
  self.assertEqual(read_json(self.hosts/(NAME+'.json'))['path'],'/another-installation/service/native-host')
 def test_fresh_install_does_not_read_an_unconnected_chatgpt_account_quota(self):
  import helper
  app=helper.App(self.base/'fresh-account')
  try:
   with patch.object(app.local_engine,'quota') as quota:
    self.assertFalse(app.quota()['available']);quota.assert_not_called()
  finally:
   app.pool.shutdown();app.local_engine.close(cleanup=True);app.antigravity.close(cleanup=True)

if __name__=='__main__':unittest.main()
