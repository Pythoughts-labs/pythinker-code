from pythinker_review.engine.structured_diff import StructuredFile, render_structured_diff

SAMPLE_DIFF = """diff --git a/src/app.py b/src/app.py
index 1111..2222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@
 def f():
-    return 1
+    return 2
+    # added
     # comment
 # tail
"""


def test_renders_file_header_and_hunks() -> None:
    out = render_structured_diff(SAMPLE_DIFF)
    assert len(out) == 1
    sf = out[0]
    assert isinstance(sf, StructuredFile)
    assert sf.path == "src/app.py"
    assert "## File: 'src/app.py'" in sf.rendered
    assert "__new hunk__" in sf.rendered
    assert "__old hunk__" in sf.rendered
    assert "2 +    return 2" in sf.rendered
    assert "3 +    # added" in sf.rendered


def test_handles_added_file() -> None:
    diff = "diff --git a/new.py b/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n+x = 1\n+y = 2\n"
    out = render_structured_diff(diff)
    assert out[0].path == "new.py"
    assert "1 +x = 1" in out[0].rendered
    assert "2 +y = 2" in out[0].rendered


def test_handles_pure_deletion_hunk() -> None:
    diff = "diff --git a/old.py b/old.py\n--- a/old.py\n+++ b/old.py\n@@ -1,2 +1,1 @@\n keep\n-removed\n"
    out = render_structured_diff(diff)
    assert "-removed" in out[0].rendered
    assert "__old hunk__" in out[0].rendered


def test_skips_binary_diffs() -> None:
    assert (
        render_structured_diff(
            "diff --git a/img.png b/img.png\nBinary files a/img.png and b/img.png differ\n"
        )
        == []
    )
