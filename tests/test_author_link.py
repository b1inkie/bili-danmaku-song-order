"""Author profile bridge regression; never actually launches a browser."""
import unittest
from unittest.mock import patch
from main_gui import Api


class AuthorLinkTests(unittest.TestCase):
    def test_fixed_profile_opens_in_system_browser(self):
        api = Api.__new__(Api)
        with patch('webbrowser.open', return_value=True) as opened:
            self.assertTrue(api.open_author_bilibili())
            opened.assert_called_once_with('https://space.bilibili.com/1160389658')

    def test_browser_failure_is_not_reported_as_success(self):
        with patch('webbrowser.open', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '无法打开系统浏览器'):
                Api.__new__(Api).open_author_bilibili()


if __name__ == '__main__':
    unittest.main()
