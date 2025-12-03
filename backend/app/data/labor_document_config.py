"""
Configuración para clasificación laboral.
Lista extensible sin hardcode.
"""

LABOR_DOCUMENT_TYPES = [
    {
        'type': 'nomina',
        'keywords': ['nómina', 'payroll', 'salary', 'sueldo', 'retenciones', 'irpf']
    },
    {
        'type': 'contrato',
        'keywords': ['contrato', 'contract', 'acuerdo', 'agreement', 'cláusula', 'duración']
    },
    {
        'type': 'certificado',
        'keywords': ['certificado', 'certificate', 'certificación', 'declaración']
    },
    {
        'type': 'modelo_111',
        'keywords': ['modelo 111', 'model 111', '111', 'retenciones irpf']
    },
    {
        'type': 'modelo_190',
        'keywords': ['modelo 190', 'model 190', '190', 'resumen anual']
    },
    {
        'type': 'modelo_303',
        'keywords': ['modelo 303', 'model 303', '303', 'iva trimestral']
    },
    {
        'type': 'comunicacion_itss',
        'keywords': ['itss', 'inspección', 'inspector', 'acta', 'sancion']
    },
]