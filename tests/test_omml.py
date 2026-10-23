from src.core.omml_converter import latex_to_omml, MATH_NS

def test_einstein():
    result = latex_to_omml(r'E = mc^2')
    assert result.tag == f'{{{MATH_NS}}}oMathPara'
    assert result.find(f'.//{{{MATH_NS}}}sSup') is not None

def test_fraction():
    result = latex_to_omml(r'\frac{a}{b}',False)
    assert result.find(f'.//{{{MATH_NS}}}f') is not None
