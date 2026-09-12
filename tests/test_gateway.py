import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
import gateway
class GatewayTests(unittest.TestCase):
 def test_url_roundtrip(self):
  u='https://例子.example/a?q=1'; self.assertEqual(gateway.decode_url(gateway.encode_url(u)),u)
 def test_default_https(self): self.assertEqual(gateway.normalize_url('example.com'),'https://example.com')
 def test_reject_file(self):
  with self.assertRaises(ValueError): gateway.normalize_url('file:///etc/passwd')
 def test_relative_link(self): self.assertEqual(gateway.decode_url(gateway.proxy_url('../x','https://a.test/p/y')[4:]),'https://a.test/x')
 def test_html_attrs(self):
  out=gateway.rewrite_content('<a href="/x"><img srcset="a.png 1x, b.png 2x">','https://a.test/p','text/html'); self.assertEqual(out.count('/_p/'),3)
 def test_css(self): self.assertIn('/_p/',gateway.rewrite_content('a{background:url(../x.png)}','https://a.test/c/a.css','text/css'))
 def test_inert_schemes(self): self.assertEqual(gateway.proxy_url('data:text/plain,x','https://a.test'),'data:text/plain,x')
 def test_session_existing(self): self.assertEqual(gateway.session_id('x=1; BDGSESSION=abcdefghijklmnopqrstuv')[0],'abcdefghijklmnopqrstuv')
if __name__=='__main__': unittest.main()
