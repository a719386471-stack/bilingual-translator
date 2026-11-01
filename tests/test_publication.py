import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_publication import audit

class PublicationTests(unittest.TestCase):
 def test_private_paths_and_data_files_are_blocked(self):
  with self.assertRaises(ValueError):audit({'connection.json':b'{}'})
  private_path='/'+'Users/'+'private-user/Documents/file'
  with self.assertRaises(ValueError):audit({'README.md':private_path.encode()})
 def test_token_shaped_literals_are_blocked(self):
  for value in ('sk-'+'a'*40,'ghp_'+'a'*40,'ya29.'+'a'*40):
   with self.subTest(kind=value[:3]),self.assertRaises(ValueError):audit({'settings.py':value.encode()})
 def test_public_identifier_and_fixture_auth_names_are_allowed(self):
  audit({'packaging/release-public-key.txt':b'public-extension-identifier',
         'tests/example.py':b'fixture_key="fixture-not-a-real-token"',
         'native_host.py':b'pairing_key = generate_at_install()'})
