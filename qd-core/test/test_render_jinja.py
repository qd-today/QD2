"""Tests for QD v1 compatible Jinja2 rendering and filters."""

import base64
import time

import pytest
from qd_core.client.render import RenderError, render_string, render_template
from qd_core.filters import jinja_extensions
from qd_core.schemas.har import HARHeader, HARPostData, HARRequest, HARTemplate


class TestRenderString:
    def test_simple_variable(self):
        assert render_string("Hello {{name}}!", {"name": "World"}) == "Hello World!"

    def test_missing_variable_renders_empty(self):
        # Jinja2 default: undefined renders as empty string
        assert render_string("Hello {{nope}}!", {}) == "Hello !"

    def test_no_template_syntax(self):
        assert render_string("plain text", {}) == "plain text"

    def test_empty_string(self):
        assert render_string("", {"a": 1}) == ""

    def test_syntax_error_raises(self):
        with pytest.raises(RenderError):
            render_string("{% invalid", {})


class TestOriginalQDFilters:
    """Each filter must behave identically to original QD."""

    def test_md5(self):
        assert render_string("{{ 'abc' | md5 }}", {}) == "900150983cd24fb0d6963f7d28e17f72"

    def test_sha1(self):
        assert render_string("{{ 'abc' | sha1 }}", {}) == "a9993e364706816aba3e25717850c26c9cd0d89d"

    def test_hash_sha256(self):
        assert (
            render_string("{{ 'abc' | hash('sha256') }}", {})
            == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_b64encode(self):
        assert render_string("{{ 'hello' | b64encode }}", {}) == base64.b64encode(b"hello").decode()

    def test_b64decode(self):
        assert render_string("{{ 'aGVsbG8=' | b64decode }}", {}) == "hello"

    def test_urlencode(self):
        assert render_string("{{ '你好' | urlencode }}", {}) == "%E4%BD%A0%E5%A5%BD"

    def test_quote_chinese(self):
        assert render_string("{{ 'ab你好' | quote_chinese }}", {}) == "ab%E4%BD%A0%E5%A5%BD"

    def test_timestamp(self):
        result = int(render_string("{{ timestamp() }}", {}))
        assert abs(result - int(time.time())) <= 2

    def test_timestamp_float(self):
        result = float(render_string("{{ timestamp('float') }}", {}))
        assert abs(result - time.time()) <= 2

    def test_unicode_escape(self):
        assert render_string(r"{{ '\u4f60\u597d' | unicode }}", {}) == "你好"

    def test_regex_replace(self):
        assert render_string("{{ 'ansible' | regex_replace('^a.*i(.*)$', 'a\\\\1') }}", {}) == "able"

    def test_regex_findall(self):
        result = render_string("{{ 'a1b2c3' | regex_findall('[0-9]') }}", {})
        assert result == "['1', '2', '3']"

    def test_regex_search(self):
        assert render_string("{{ 'foobar' | regex_search('o+') }}", {}) == "oo"

    def test_ternary_true(self):
        assert render_string("{{ True | ternary('yes', 'no') }}", {}) == "yes"

    def test_ternary_false(self):
        assert render_string("{{ False | ternary('yes', 'no') }}", {}) == "no"

    def test_add(self):
        assert float(render_string("{{ add(1, 2) }}", {})) == 3.0

    def test_sub(self):
        assert float(render_string("{{ sub(5, 2) }}", {})) == 3.0

    def test_multiply(self):
        assert float(render_string("{{ multiply(3, 4) }}", {})) == 12.0

    def test_divide(self):
        assert float(render_string("{{ divide(10, 4) }}", {})) == 2.5

    def test_is_num(self):
        assert render_string("{{ is_num('3.14') }}", {}) == "True"
        assert render_string("{{ is_num('abc') }}", {}) == "False"

    def test_random_range(self):
        result = float(render_string("{{ random(1, 10, 2) }}", {}))
        assert 1.0 <= result <= 10.0

    def test_int_float_filters(self):
        assert render_string("{{ '42' | int }}", {}) == "42"
        assert render_string("{{ '3.5' | float }}", {}) == "3.5"

    def test_bool_filter(self):
        assert render_string("{{ 'yes' | bool }}", {}) == "True"
        assert render_string("{{ 'no' | bool }}", {}) == "False"

    def test_aes_encrypt_decrypt_roundtrip(self):
        tpl = "{{ aes_encrypt('secret data', '0123456789abcdef', 'ECB') }}"
        encrypted = render_string(tpl, {}).strip()
        tpl2 = f"{{{{ aes_decrypt({encrypted!r}, '0123456789abcdef', 'ECB') }}}}"
        assert render_string(tpl2, {}) == "secret data"

    def test_to_uuid_deterministic(self):
        a = render_string("{{ 'example.com' | to_uuid }}", {})
        b = render_string("{{ 'example.com' | to_uuid }}", {})
        assert a == b and len(a) == 36

    def test_date_time(self):
        result = render_string("{{ date_time() }}", {})
        assert len(result) == 19  # 'YYYY-MM-DD HH:MM:SS'

    def test_mandatory_defined(self):
        assert render_string("{{ x | mandatory }}", {"x": "v"}) == "v"

    def test_mandatory_undefined_raises(self):
        with pytest.raises(RenderError):
            render_string("{{ nope | mandatory }}", {})

    def test_inner_globals_range(self):
        assert render_string("{% for i in range(3) %}{{i}}{% endfor %}", {}) == "012"

    def test_list_global_and_trim_filters(self):
        assert render_string("{{ list('ab') | join('-') }}", {}) == "a-b"
        assert render_string("{{ '  left  ' | ltrim }}", {}) == "left  "
        assert render_string("{{ '  right  ' | rtrim }}", {}) == "  right"

    def test_original_loop_aliases(self):
        template = "{% for item in ['a', 'b'] %}{{loop_index0}}:{{item}}/{{loop_length}};{% endfor %}"
        assert render_string(template, {}) == "0:a/2;1:b/2;"

    def test_original_while_tag(self):
        template = "{% while loop_index0 < 3 %}{{loop_index}}{% endwhile %}"
        assert render_string(template, {}) == "123"

    def test_original_while_tag_enforces_iteration_limit(self, monkeypatch):
        monkeypatch.setattr(jinja_extensions, "MAX_WHILE_ITERATIONS", 2)

        with pytest.raises(RenderError, match="while loop exceeded 2 iterations"):
            render_string("{% while true %}loop{% endwhile %}", {})

    def test_cookies_access(self):
        assert render_string("{{ _cookies['token'] }}", {}, cookies={"token": "abc123"}) == "abc123"


class TestRenderTemplate:
    def test_template_render_with_filters(self):
        template = HARTemplate(
            name="t",
            variables={"user": "alice", "pwd": "s3cret"},
            requests=[
                HARRequest(
                    url="https://example.com/login?u={{user}}",
                    headers=[HARHeader(name="X-Sign", value="{{ pwd | md5 }}")],
                    postData=HARPostData(text="password={{ pwd | urlencode }}"),
                )
            ],
        )
        rendered = render_template(template)
        req = rendered.requests[0]
        assert req.url == "https://example.com/login?u=alice"
        assert req.headers[0].value == "33e1b232a4e6fa0028a6670753749a17"
        assert req.postData.text == "password=s3cret"

    def test_runtime_variable_override(self):
        template = HARTemplate(
            name="t",
            variables={"who": "default"},
            requests=[HARRequest(url="https://x.com/{{who}}")],
        )
        rendered = render_template(template, {"who": "override"})
        assert rendered.requests[0].url == "https://x.com/override"
