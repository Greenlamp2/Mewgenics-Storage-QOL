"""Quick sanity check for the changelog Markdown converter."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ui.changelog_panel import _markdown_to_html

def test_raw_img_tag():
    line = '<img width="1059" height="492" alt="image" src="https://github.com/user-attachments/assets/c255a7c7-7978-4dda-a747-2f79861823de" />'
    result = _markdown_to_html(line)
    assert '&lt;img' not in result, f"Tag img still escaped: {result}"
    assert 'src="https://github.com/user-attachments/assets/c255a7c7' in result, f"src URL missing: {result}"
    assert '<p style="text-align:center' in result, f"Not centred: {result}"
    print("PASS  test_raw_img_tag")

def test_markdown_img():
    line = "![Screenshot](https://example.com/img.png)"
    result = _markdown_to_html(line)
    assert '&lt;img' not in result
    assert 'src="https://example.com/img.png"' in result
    print("PASS  test_markdown_img")

def test_raw_img_not_escaped_in_text():
    line = 'Check this out: <img alt="demo" src="https://example.com/x.png" /> nice!'
    result = _markdown_to_html(line)
    assert '&lt;img' not in result
    assert 'src="https://example.com/x.png"' in result
    print("PASS  test_raw_img_not_escaped_in_text")

def test_normal_text_still_escaped():
    line = '<b>this is not a tag we want</b>'
    result = _markdown_to_html(line)
    assert '&lt;b&gt;' in result
    print("PASS  test_normal_text_still_escaped")

if __name__ == "__main__":
    test_raw_img_tag()
    test_markdown_img()
    test_raw_img_not_escaped_in_text()
    test_normal_text_still_escaped()
    print("All tests passed.")

