"""HAR template parser for QD2.

Parses HAR files and QD2 template format into HARTemplate objects.
Handles variable substitution and template validation.
"""

import json
from pathlib import Path
from typing import Any, Optional

from qd_core.schemas.har import HARData, HARRequest, HARTemplate
from qd_core.utils.log import Log

logger = Log("QD.Core.HARParser").getlogger()


class HARParser:
    """Parser for HAR files and QD2 template format.

    Supports:
    - Standard HAR 1.2 files
    - QD2 native template format (JSON)
    - Variable substitution in templates
    """

    @staticmethod
    def parse_file(file_path: str | Path) -> HARTemplate:
        """Parse a HAR file or QD2 template file.

        Args:
            file_path: Path to the HAR or template file.

        Returns:
            Parsed HARTemplate object.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file format is invalid.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Template file not found: {path}")

        content = path.read_text(encoding="utf-8")
        data = json.loads(content)

        return HARParser.parse_dict(data, source_file=str(path))

    @staticmethod
    def parse_dict(data: dict[str, Any] | list, source_file: Optional[str] = None) -> HARTemplate:
        """Parse a dictionary into a HARTemplate.

        Detects whether the input is standard HAR, QD2 format, or QD v1
        tpl format (a JSON list of ``{request, rule}`` entries — the format
        used by the qd-today/templates public repository).

        Args:
            data: Dictionary or list containing template data.
            source_file: Source file path for metadata.

        Returns:
            Parsed HARTemplate object.
        """
        # QD v1 tpl format: top-level list of {request, rule} entries
        if isinstance(data, list):
            return HARParser._parse_qd1_tpl(data, source_file)

        # Check if it's a QD2 native template
        if "requests" in data and "name" in data:
            return HARTemplate(**data)

        # Check if it's standard HAR format
        if "log" in data:
            return HARParser._parse_har_log(data["log"], source_file)

        raise ValueError("Invalid template format: expected 'requests' or 'log' key")

    @staticmethod
    def _parse_qd1_tpl(entries: list, source_file: Optional[str] = None) -> HARTemplate:
        """Parse the original QD tpl format (list of {request, rule} entries).

        This is the format used by https://github.com/qd-today/templates.
        Request bodies are stored as ``request.data`` + ``request.mimeType``
        instead of HAR's ``postData`` structure.
        """
        from qd_core.schemas.har import HARPostData, RequestRule

        requests = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            req_src = entry.get("request")
            if not req_src:
                continue

            req_data = dict(req_src)
            # QD v1 stores body as 'data' + 'mimeType' rather than postData
            body_text = req_data.pop("data", None)
            mime_type = req_data.pop("mimeType", None)
            if body_text and "postData" not in req_data:
                req_data["postData"] = HARPostData(
                    mimeType=mime_type or "application/x-www-form-urlencoded",
                    text=body_text,
                ).model_dump()

            request = HARRequest(**req_data)

            rule_src = entry.get("rule") or {}
            if any(rule_src.get(k) for k in ("success_asserts", "failed_asserts", "extract_variables")):
                request.rule = RequestRule(
                    success_asserts=rule_src.get("success_asserts", []),
                    failed_asserts=rule_src.get("failed_asserts", []),
                    extract_variables=rule_src.get("extract_variables", []),
                )

            requests.append(request)

        if not requests:
            raise ValueError("Invalid QD v1 tpl: no request entries found")

        name = Path(source_file).stem if source_file else "imported_template"
        return HARTemplate(
            name=name,
            description="Imported from QD v1 tpl",
            version="1.0",
            requests=requests,
        )

    @staticmethod
    def _parse_har_log(log: dict[str, Any], source_file: Optional[str] = None) -> HARTemplate:
        """Parse a HAR log object into a HARTemplate.

        Supports original QD HAR exports: entry-level ``success_asserts`` /
        ``failed_asserts`` / ``extract_variables`` (or nested ``rule`` blocks)
        are mapped onto each request's ``rule`` field, and unchecked entries
        (``checked: false``) are skipped.

        Args:
            log: The 'log' section of a HAR file.
            source_file: Source file path.

        Returns:
            Parsed HARTemplate.
        """
        from qd_core.schemas.har import RequestRule

        entries = log.get("entries", [])
        requests = []

        for entry in entries:
            har_request = entry.get("request", {})
            if not har_request:
                continue
            # QD v1 export marks entries the user disabled with checked=false
            if entry.get("checked") is False:
                continue

            request = HARRequest(**har_request)

            # QD v1 rule block: either flattened on the entry or nested under 'rule'
            rule_src = entry.get("rule") or {}
            success_asserts = entry.get("success_asserts", rule_src.get("success_asserts", []))
            failed_asserts = entry.get("failed_asserts", rule_src.get("failed_asserts", []))
            extract_variables = entry.get("extract_variables", rule_src.get("extract_variables", []))
            if success_asserts or failed_asserts or extract_variables:
                request.rule = RequestRule(
                    success_asserts=success_asserts,
                    failed_asserts=failed_asserts,
                    extract_variables=extract_variables,
                )

            requests.append(request)

        creator = log.get("creator", {})
        name = Path(source_file).stem if source_file else "imported_template"

        return HARTemplate(
            name=name,
            description="Imported from HAR file",
            version="1.0",
            requests=requests,
            author=creator.get("comment", ""),
        )

    @staticmethod
    def substitute_variables(text: str, variables: dict[str, Any]) -> str:
        """Substitute template variables in a string.

        Variables are referenced as {{variable_name}} in the template.

        Args:
            text: Text containing variable references.
            variables: Dictionary of variable values.

        Returns:
            Text with variables substituted.

        Example:
            >>> HARParser.substitute_variables("Hello {{name}}!", {"name": "World"})
            'Hello World!'
        """
        result = text
        for key, value in variables.items():
            placeholder = "{{" + key + "}}"
            result = result.replace(placeholder, str(value))
        return result

    @staticmethod
    def export_template(template: HARTemplate, output_path: str | Path) -> None:
        """Export a HARTemplate to a JSON file.

        Args:
            template: The template to export.
            output_path: Path to write the JSON file.
        """
        path = Path(output_path)
        data = template.model_dump(mode="json", exclude_none=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Template exported to %s", path)
