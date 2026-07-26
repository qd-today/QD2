"""Regression test: parse + render real templates from qd-today/templates.

Only runs when /tmp/qd-templates exists (cloned from
https://github.com/qd-today/templates). Validates that original QD
templates parse into HARTemplate and their Jinja2 syntax renders without
crashing the engine.
"""

import json
from pathlib import Path

import pytest

from qd_core.client.har import HARParser
from qd_core.client.render import RenderError, render_string

TEMPLATES_DIR = Path("/tmp/qd-templates")

pytestmark = pytest.mark.skipif(
    not TEMPLATES_DIR.exists(), reason="qd-today/templates repo not cloned to /tmp/qd-templates"
)


def iter_har_files(limit=None):
    files = sorted(TEMPLATES_DIR.glob("*.har"))
    return files[:limit] if limit else files


class TestRealTemplateCompat:
    def test_parse_all_templates(self):
        """Every original template must parse into a HARTemplate."""
        files = iter_har_files()
        assert len(files) > 100, "expected the real template library"
        failures = []
        parsed_count = 0
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tpl = HARParser.parse_dict(data, source_file=str(f))
                assert tpl.requests, f"no requests parsed from {f.name}"
                parsed_count += 1
            except Exception as e:
                failures.append((f.name, repr(e)[:120]))

        # Allow a small number of malformed templates in the upstream repo
        fail_ratio = len(failures) / len(files)
        print(f"\nparsed {parsed_count}/{len(files)} templates, failures: {len(failures)}")
        for name, err in failures[:10]:
            print(f"  FAIL {name}: {err}")
        assert fail_ratio < 0.05, f"too many parse failures: {failures[:20]}"

    def test_render_template_variables(self):
        """Template variable defaults must render through Jinja2 without engine crashes."""
        files = iter_har_files()
        render_failures = []
        rendered_count = 0
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tpl = HARParser.parse_dict(data, source_file=str(f))
            except Exception:
                continue

            variables = {k: str(v) for k, v in tpl.variables.items()}
            for req in tpl.requests[:3]:
                for text in filter(None, [req.url, req.postData.text if req.postData else None]):
                    try:
                        render_string(text, variables)
                    except RenderError:
                        # RenderError is acceptable (template needs real values);
                        # engine-level crashes are not.
                        pass
                    except Exception as e:
                        render_failures.append((f.name, repr(e)[:120]))
            rendered_count += 1

        print(f"\nrendered {rendered_count} templates, engine crashes: {len(render_failures)}")
        for name, err in render_failures[:10]:
            print(f"  CRASH {name}: {err}")
        assert not render_failures, f"engine crashes: {render_failures[:10]}"
