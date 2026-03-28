from PyQt6.QtGui import QTextCharFormat, QColor
from PyQt6.QtCore import QRegularExpression
from plugins.languages.javascript_plugin import JavaScriptPlugin


class TypeScriptPlugin(JavaScriptPlugin):
    EXTENSIONS = ['.ts', '.tsx', '.mts', '.cts']

    def __init__(self):
        # Inherit all JavaScript rules then add TS-specific ones on top
        super().__init__()

        # TypeScript-only keywords
        self.add_rule(
            r'\b(abstract|as|asserts|declare|enum|from|global|implements|'
            r'interface|is|keyof|module|namespace|never|override|readonly|'
            r'satisfies|type|unique|unknown|infer|out|accessor)\b',
            'keyword'
        )

        # Type primitives
        type_fmt = QTextCharFormat()
        type_fmt.setForeground(QColor("#4EC9B0"))
        self.add_rule_fmt(
            r'\b(string|number|boolean|symbol|bigint|object|any|void|'
            r'null|undefined|never|unknown)\b',
            type_fmt
        )

        # Built-in utility types
        utility_fmt = QTextCharFormat()
        utility_fmt.setForeground(QColor("#4EC9B0"))
        utility_fmt.setFontItalic(True)
        self.add_rule_fmt(
            r'\b(Partial|Required|Readonly|Record|Pick|Omit|Exclude|Extract|'
            r'NonNullable|ReturnType|InstanceType|Parameters|ConstructorParameters|'
            r'Awaited|ThisType|Uppercase|Lowercase|Capitalize|Uncapitalize|'
            r'Promise|Array|Map|Set|WeakMap|WeakRef|Iterator)\b',
            utility_fmt
        )

        # interface / type declarations — highlight the name
        iface_fmt = QTextCharFormat()
        iface_fmt.setForeground(QColor("#A6E22E"))
        iface_fmt.setFontItalic(True)
        self.add_rule_fmt(r'\binterface\s+(\w+)', iface_fmt)
        self.add_rule_fmt(r'\btype\s+(\w+)\s*=',  iface_fmt)
        self.add_rule_fmt(r'\benum\s+(\w+)',       iface_fmt)

        # Generic type parameters <T>, <K, V>, <T extends U>
        generic_fmt = QTextCharFormat()
        generic_fmt.setForeground(QColor("#4EC9B0"))
        self.add_rule_fmt(r'<[A-Z]\w*(?:\s*,\s*[A-Z]\w*)*>', generic_fmt)

        # Type annotations  : string,  : number[],  : Record<string, any>
        annotation_fmt = QTextCharFormat()
        annotation_fmt.setForeground(QColor("#4EC9B0"))
        self.add_rule_fmt(r':\s*[A-Z]\w*(?:<[^>]*>)?(?:\[\])*', annotation_fmt)

        # Access modifiers
        modifier_fmt = QTextCharFormat()
        modifier_fmt.setForeground(QColor("#C586C0"))
        modifier_fmt.setFontItalic(True)
        self.add_rule_fmt(
            r'\b(public|private|protected|static|readonly|abstract|override|'
            r'declare|async)\b',
            modifier_fmt
        )

        # Decorators @Component, @Injectable etc (common in Angular/NestJS)
        decorator_fmt = QTextCharFormat()
        decorator_fmt.setForeground(QColor("#A6E22E"))
        decorator_fmt.setFontItalic(True)
        self.add_rule_fmt(r'@\w+(?:\([^)]*\))?', decorator_fmt)

        # Non-null assertion operator  value!
        nonnull_fmt = QTextCharFormat()
        nonnull_fmt.setForeground(QColor("#F92672"))
        nonnull_fmt.setFontItalic(True)
        self.add_rule_fmt(r'\w+!(?=[.\[(])', nonnull_fmt)

        # Type assertion  as Type  and  <Type>expr
        assertion_fmt = QTextCharFormat()
        assertion_fmt.setForeground(QColor("#66D9EF"))
        self.add_rule_fmt(r'\bas\s+[A-Z]\w*(?:<[^>]*>)?(?:\[\])*', assertion_fmt)

        # TSX — JSX tags inside .tsx files
        jsx_tag_fmt = QTextCharFormat()
        jsx_tag_fmt.setForeground(QColor("#F92672"))
        self.add_rule_fmt(r'</?[A-Z]\w*', jsx_tag_fmt)   # component tags
        self.add_rule_fmt(r'</?[a-z]\w*', jsx_tag_fmt)   # html tags in JSX

        # JSX attribute names
        jsx_attr_fmt = QTextCharFormat()
        jsx_attr_fmt.setForeground(QColor("#A6E22E"))
        self.add_rule_fmt(r'\b\w+(?==(?:["{]))', jsx_attr_fmt)