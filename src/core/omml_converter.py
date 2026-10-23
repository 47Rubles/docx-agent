"""LaTeX -> MathML -> native Word OMML. No plain-text math fallback."""
from pathlib import Path
import re
from lxml import etree
from docx.oxml.ns import qn

MATH_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
XSL_PATH = Path(__file__).resolve().parents[2] / 'assets/xslt/MML2OMML.XSL'

class FormulaConversionError(ValueError):
    pass

# This lightweight stylesheet does not support arbitrary TeX macros.
# Reject unknown control words rather than silently emitting an incorrect formula.
SUPPORTED_COMMANDS = frozenset("""
frac dfrac tfrac sqrt alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta
iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi
varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
cdot times div pm mp le leq ge geq neq approx equiv sim propto infty partial
sum prod int iint iiint lim log ln sin cos tan cot sec csc sinh cosh tanh
rightarrow leftarrow leftrightarrow Rightarrow Leftarrow Leftrightarrow to mapsto
in notin subset subseteq supset supseteq cup cap forall exists neg land lor
text mathrm mathbf mathit operatorname overline underline hat bar vec dot ddot
left right big Big bigg Bigg, quad qquad displaystyle textstyle,
""".replace(',', ' ').split())

def _validate_commands(latex: str) -> None:
    # Remove escaped backslashes and escaped punctuation before scanning commands.
    text = re.sub(r"\\(?:[{}_$%&#,;:!| ])", "", latex)
    for command in re.findall(r"\\([a-zA-Z]+)", text):
        if command not in SUPPORTED_COMMANDS:
            raise FormulaConversionError(f"Unsupported LaTeX command: \\{command}")

def latex_to_omml(latex: str, display: bool = True) -> etree._Element:
    try:
        _validate_commands(latex)
        try:
            import latex2mathml.converter
            mathml = latex2mathml.converter.convert(latex)
        except ImportError:
            mathml = _basic_mathml(latex)
        root = etree.fromstring(mathml.encode())
        if not XSL_PATH.exists():
            raise FormulaConversionError('MML2OMML.XSL missing: install official Microsoft stylesheet in assets/xslt; no lossy fallback')
        transform = etree.XSLT(etree.parse(str(XSL_PATH)))
        converted = transform(root).getroot()
        if converted is None:
            raise FormulaConversionError('XSLT returned empty result')
        omath = converted if converted.tag == f'{{{MATH_NS}}}oMath' else converted.find(f'.//{{{MATH_NS}}}oMath')
        if omath is None:
            raise FormulaConversionError('XSLT did not produce m:oMath')
        if display:
            para = etree.Element(f'{{{MATH_NS}}}oMathPara', nsmap={'m':MATH_NS})
            para.append(etree.fromstring(etree.tostring(omath)))
            return para
        return etree.fromstring(etree.tostring(omath))
    except FormulaConversionError:
        raise
    except Exception as exc:
        raise FormulaConversionError(f'Could not convert LaTeX formula {latex!r}: {exc}') from exc


def _basic_mathml(latex: str) -> str:
    """Limited offline fallback for simple math only; use latex2mathml for real LaTeX."""
    import re
    from xml.sax.saxutils import escape
    ns = 'http://www.w3.org/1998/Math/MathML'
    frac = re.fullmatch(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', latex.strip())
    if frac:
        return f'<math xmlns="{ns}"><mfrac><mi>{escape(frac[1])}</mi><mi>{escape(frac[2])}</mi></mfrac></math>'
    parts = []
    for tok in re.findall(r'[A-Za-z]+\^[0-9]+|[A-Za-z]+|[0-9]+|[^\s]', latex):
        if '^' in tok:
            base, exp = tok.split('^',1)
            parts.append(f'<msup><mi>{escape(base)}</mi><mn>{escape(exp)}</mn></msup>')
        else:
            tag = 'mn' if tok.isdigit() else 'mi' if tok.isalpha() else 'mo'
            parts.append(f'<{tag}>{escape(tok)}</{tag}>')
    if not parts or '\\' in latex or '{' in latex or '}' in latex:
        raise FormulaConversionError('Install latex2mathml for this LaTeX expression')
    return f'<math xmlns="{ns}"><mrow>{"".join(parts)}</mrow></math>'
