from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression


class TerraformPlugin(LanguagePlugin):
    """
    Syntax highlighting for Terraform / OpenTofu HCL files.
    Supports .tf and .tfvars files.
    """
    EXTENSIONS = ['.tf', '.tfvars', '.hcl']

    def __init__(self):
        super().__init__()

        # ── Block keywords ────────────────────────────────────────────────
        # resource, data, module, variable, output, locals, terraform, etc.
        block_keywords = [
            r'\bresource\b', r'\bdata\b', r'\bmodule\b', r'\bvariable\b',
            r'\boutput\b', r'\blocals\b', r'\bterraform\b', r'\bprovider\b',
            r'\bprovisioner\b', r'\bbackend\b', r'\brequired_providers\b',
            r'\brequired_version\b', r'\bmoved\b', r'\bimport\b',
            r'\bchecks\b', r'\bassert\b',
        ]
        for kw in block_keywords:
            self.add_rule(kw, 'keyword')

        # ── Expression keywords ───────────────────────────────────────────
        expr_keywords = [
            r'\bfor\b', r'\bin\b', r'\bif\b', r'\belse\b',
            r'\bnull\b', r'\btrue\b', r'\bfalse\b',
            r'\bany\b', r'\ball\b',
        ]
        for kw in expr_keywords:
            self.add_rule(kw, 'keyword')

        # ── Built-in functions ────────────────────────────────────────────
        builtins = [
            r'\babs\b', r'\bceil\b', r'\bfloor\b', r'\blog\b', r'\bmax\b',
            r'\bmin\b', r'\bpow\b', r'\bsignum\b',
            r'\bchomp\b', r'\bformat\b', r'\bformatlist\b', r'\bindent\b',
            r'\bjoin\b', r'\blower\b', r'\bregex\b', r'\bregexall\b',
            r'\breplace\b', r'\bsplit\b', r'\bstrrev\b', r'\bsubstr\b',
            r'\btitle\b', r'\btrimspace\b', r'\bupper\b',
            r'\bbase64decode\b', r'\bbase64encode\b', r'\bbase64gzip\b',
            r'\bcsvdecode\b', r'\bjsondecode\b', r'\bjsonencode\b',
            r'\btoml\b', r'\burlencode\b', r'\byamldecode\b', r'\byamlencode\b',
            r'\bcoalesce\b', r'\bcoalescelist\b', r'\bcompact\b',
            r'\bconcat\b', r'\bcontains\b', r'\bdistinct\b', r'\belement\b',
            r'\bflatten\b', r'\bindex\b', r'\bkeys\b', r'\blength\b',
            r'\blist\b', r'\blookup\b', r'\bmap\b', r'\bmatchkeys\b',
            r'\bmerge\b', r'\brange\b', r'\breverse\b', r'\bsetintersection\b',
            r'\bsetproduct\b', r'\bsetsubtract\b', r'\bsetunion\b',
            r'\bslice\b', r'\bsort\b', r'\btranspose\b', r'\bvalues\b',
            r'\bzipmap\b',
            r'\bfile\b', r'\bfilebase64\b', r'\bfileexists\b',
            r'\bfileset\b', r'\bfilemd5\b', r'\bfilesha1\b', r'\bfilesha256\b',
            r'\bpathexpand\b', r'\bdirnamebase\b',
            r'\bcidrhost\b', r'\bcidrnetmask\b', r'\bcidrsubnet\b',
            r'\bcidrsubnets\b',
            r'\bcan\b', r'\btry\b', r'\btype\b',
            r'\btostring\b', r'\btonumber\b', r'\btobool\b',
            r'\btoset\b', r'\btolist\b', r'\btomap\b',
            r'\btimestamp\b', r'\btimeadd\b', r'\bformatdate\b',
        ]
        for fn in builtins:
            self.add_rule(fn, 'builtin')

        # ── Resource / data source type (first string after resource/data) ─
        # e.g. resource "aws_instance" "web" {
        self.add_rule(r'(?<=resource\s)"[\w]+"', 'class_def')
        self.add_rule(r'(?<=data\s)"[\w]+"', 'class_def')
        self.add_rule(r'(?<=module\s)"[\w]+"', 'func_def')
        self.add_rule(r'(?<=provider\s)"[\w]+"', 'func_def')

        # ── Attribute names (word before =) ──────────────────────────────
        self.add_rule(r'\b\w+\s*(?==(?!=))', 'keyword')

        # ── References: var.x, local.x, data.x, module.x ─────────────────
        self.add_rule(r'\b(var|local|data|module|path|terraform|each|count|'
                      r'self)\.\w+', 'builtin')

        # ── Numbers ───────────────────────────────────────────────────────
        self.add_rule(r'\b[0-9]+(\.[0-9]+)?\b', 'number')

        # ── Strings ───────────────────────────────────────────────────────
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')

        # ── Template interpolation ${ ... } ──────────────────────────────
        self.add_rule(r'\$\{[^}]*\}', 'string2')

        # ── Template directives %{ ... } ─────────────────────────────────
        self.add_rule(r'%\{[^}]*\}', 'builtin')

        # ── Operators ────────────────────────────────────────────────────
        self.add_rule(r'[=><!\+\-\*\/\?\:]', 'operator')

        # ── Comments ─────────────────────────────────────────────────────
        self.add_rule(r'#[^\n]*', 'comment')
        self.add_rule(r'//[^\n]*', 'comment')

        # ── Multiline comments /* ... */ ──────────────────────────────────
        self.multiline_start  = QRegularExpression(r'/\*')
        self.multiline_end    = QRegularExpression(r'\*/')
        self.multiline_format = THEME['comment']

        # ── Heredoc strings (<<-EOT ... EOT) ─────────────────────────────
        # Basic detection — marks the opening line
        self.add_rule(r'<<[-]?\w+', 'string')