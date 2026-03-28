from PyQt6.QtGui import QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression
from editor.highlighter import LanguagePlugin


class JavaScriptPlugin(LanguagePlugin):
    EXTENSIONS = ['.js', '.mjs', '.cjs']

    def __init__(self):
        super().__init__()

        # Keywords
        self.add_rule(
            r'\b(break|case|catch|class|const|continue|debugger|default|delete|'
            r'do|else|export|extends|finally|for|function|if|import|in|instanceof|'
            r'let|new|of|return|static|super|switch|throw|try|typeof|var|void|'
            r'while|with|yield|async|await)\b',
            'keyword'
        )

        # Built-ins and globals
        self.add_rule(
            r'\b(console|window|document|process|module|exports|require|'
            r'Promise|Array|Object|String|Number|Boolean|Symbol|BigInt|'
            r'Math|Date|JSON|RegExp|Error|Map|Set|WeakMap|WeakSet|'
            r'parseInt|parseFloat|isNaN|isFinite|encodeURI|decodeURI|'
            r'setTimeout|setInterval|clearTimeout|clearInterval|fetch|'
            r'undefined|null|true|false|NaN|Infinity|globalThis|'
            r'arguments|prototype|constructor)\b',
            'builtin'
        )

        # Class and function definitions — highlight the name
        self.add_rule(r'\bclass\s+(\w+)', 'class_def')
        self.add_rule(r'\bfunction\s+(\w+)', 'func_def')

        # Arrow functions assigned to const/let
        arrow_fmt = QTextCharFormat()
        arrow_fmt.setForeground(QColor("#A6E22E"))
        self.add_rule_fmt(
            r'\b(const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(',
            arrow_fmt
        )

        # Numbers — integer, float, hex, octal, binary, BigInt
        self.add_rule(
            r'\b(0x[0-9A-Fa-f]+|0o[0-7]+|0b[01]+|\d+\.?\d*([eE][+-]?\d+)?n?)\b',
            'number'
        )

        # Template literals — `string ${expr}`
        template_fmt = QTextCharFormat()
        template_fmt.setForeground(QColor("#E6DB74"))
        self.add_rule_fmt(r'`[^`]*`', template_fmt)

        # Regular strings
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')
        self.add_rule(r"'[^'\\]*(\\.[^'\\]*)*'", 'string')

        # Regular expressions  /pattern/flags
        regex_fmt = QTextCharFormat()
        regex_fmt.setForeground(QColor("#E6DB74"))
        regex_fmt.setFontItalic(True)
        self.add_rule_fmt(r'/(?!\*)[^\n/\\]*(?:\\.[^\n/\\]*)*/[gimsuy]*', regex_fmt)

        # Decorators (@decorator)
        decorator_fmt = QTextCharFormat()
        decorator_fmt.setForeground(QColor("#A6E22E"))
        self.add_rule_fmt(r'@\w+', decorator_fmt)

        # JSDoc tags (@param, @returns, etc.) inside comments
        jsdoc_fmt = QTextCharFormat()
        jsdoc_fmt.setForeground(QColor("#569CD6"))
        jsdoc_fmt.setFontItalic(True)
        self.add_rule_fmt(r'@\b(param|returns?|type|typedef|property|prop|'
                          r'async|yields?|throws?|deprecated|since|version|'
                          r'author|see|link|example|class|constructor)\b',
                          jsdoc_fmt)

        # Single-line comments //
        self.add_rule(r'//[^\n]*', 'comment')

        # Multiline block comments /* ... */
        self.multiline_start = QRegularExpression(r'/\*')
        self.multiline_end   = QRegularExpression(r'\*/')
        self.multiline_format = QTextCharFormat()
        self.multiline_format.setForeground(QColor("#75715E"))
        self.multiline_format.setFontItalic(True)