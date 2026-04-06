# plugins/languages/docker_compose_plugin.py
from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression


class DockerComposePlugin(LanguagePlugin):
    """
    Enhanced YAML highlighting for docker-compose files.
    Loaded for docker-compose.yml / docker-compose.yaml specifically.
    """
    EXTENSIONS = []   # filename-matched only
    FILENAMES  = [
        'docker-compose.yml', 'docker-compose.yaml',
        'docker-compose.dev.yml', 'docker-compose.prod.yml',
        'docker-compose.override.yml', 'compose.yml', 'compose.yaml',
    ]

    def __init__(self):
        super().__init__()

        # Top-level compose keys
        top_level = [
            r'\bservices\b', r'\bvolumes\b', r'\bnetworks\b',
            r'\bconfigs\b', r'\bsecrets\b', r'\bversion\b',
        ]
        for kw in top_level:
            self.add_rule(kw, 'keyword')

        # Service definition keys
        service_keys = [
            r'\bimage\b', r'\bbuild\b', r'\bcontainer_name\b',
            r'\bcommand\b', r'\bentrypoint\b', r'\benvironment\b',
            r'\benv_file\b', r'\bports\b', r'\bvolumes\b',
            r'\bdepends_on\b', r'\bnetworks\b', r'\brestart\b',
            r'\bhealthcheck\b', r'\blabels\b', r'\bprofiles\b',
            r'\bdeploy\b', r'\bscale\b', r'\breplicas\b',
            r'\blinks\b', r'\bexpose\b', r'\bextra_hosts\b',
            r'\bdns\b', r'\bcap_add\b', r'\bcap_drop\b',
            r'\bprivileged\b', r'\buser\b', r'\bworking_dir\b',
            r'\bstdin_open\b', r'\btty\b', r'\bloggging\b',
            r'\bplatform\b', r'\bpull_policy\b',
        ]
        for kw in service_keys:
            self.add_rule(kw, 'builtin')

        # Restart policies
        self.add_rule(
            r'\b(always|unless-stopped|on-failure|no)\b', 'number'
        )

        # Port mappings
        self.add_rule(r'\b\d+:\d+\b', 'string2')

        # Image tags (name:tag)
        self.add_rule(r'[\w\-\.\/]+:[\w\-\.]+', 'string')

        # Variables
        self.add_rule(r'\$\{[\w]+(?::-[^}]*)?\}', 'string2')
        self.add_rule(r'\$[\w]+', 'string2')

        # Strings
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')
        self.add_rule(r"'[^'\\]*(\\.[^'\\]*)*'", 'string')

        # Booleans
        self.add_rule(r'\b(true|false|yes|no|null|~)\b', 'keyword')

        # Numbers
        self.add_rule(r'\b[0-9]+\b', 'number')

        # Comments
        self.add_rule(r'#[^\n]*', 'comment')

        # List dashes
        self.add_rule(r'^\s*-\s', 'operator')