"""Versioned, deterministic synthetic corpus. All organizations and values are fictional."""

# Each policy contributes two pages and seven questions. Organizations and
# policy families are disjoint between development and held-out sets.
POLICIES = {
    "development": [
        ("Arandu", "viagens técnicas", "VT-241", "Logística", "trecho rodoviário", 8, 12, "12/02/2026", "R$ 480,00"),
        ("Boré", "calibração de sensores", "CS-692", "Metrologia", "sensor óptico", 14, 21, "03/04/2026", "R$ 1.175,00"),
        ("Cauá", "devolução de uniformes", "DU-783", "Almoxarifado", "jaqueta térmica", 5, 9, "18/05/2026", "R$ 155,00"),
        ("Dourana", "manutenção de bombas", "MB-339", "Engenharia", "bomba centrífuga", 17, 23, "07/06/2026", "R$ 2.350,00"),
        ("Embaúba", "acesso a laboratórios", "AL-475", "Segurança", "câmara úmida", 3, 6, "25/07/2026", "R$ 315,00"),
        ("Figueiral", "locação de veículos", "LV-568", "Frotas", "utilitário elétrico", 13, 19, "09/08/2026", "R$ 940,00"),
    ],
    "heldout": [
        ("Guaimbê", "amostras de água", "AA-527", "Controle Ambiental", "frasco âmbar", 7, 15, "21/01/2026", "R$ 785,00"),
        ("Helicon", "inspeção de elevadores", "IE-645", "Facilities", "elevador panorâmico", 11, 18, "08/03/2026", "R$ 3.125,00"),
        ("Ingazeiro", "reposição de ferramentas", "RF-179", "Oficina", "torquímetro digital", 9, 16, "16/04/2026", "R$ 640,00"),
        ("Jatobina", "entrega de brindes", "EB-486", "Comunicação", "kit promocional", 4, 10, "27/05/2026", "R$ 270,00"),
        ("Limoara", "auditoria de estoque", "AE-891", "Inventário", "etiqueta NFC", 16, 24, "11/06/2026", "R$ 1.490,00"),
        ("Macaúral", "restauração de arquivos", "RA-765", "Arquivo Técnico", "mídia magnética", 6, 20, "14/08/2026", "R$ 2.215,00"),
    ],
}

MISSING_QUESTIONS = [
    "Qual é o telefone do plantão?", "Qual foi a receita anual?",
    "Qual é o endereço do fornecedor?", "Em que ano a empresa foi fundada?",
    "Qual é a multa por atraso?", "Qual é o número de registro fiscal?",
]


def dataset():
    corpus, cases = [], []
    for split, policies in POLICIES.items():
        for i, (org, topic, code, team, item, days, previous, date, value) in enumerate(policies):
            did = len(corpus) // 2 + 1
            filename = f"{org.lower()}-norma.txt"
            pages = [
                f"{org} — norma vigente de {topic}. O protocolo {code} é aprovado por {team}. "
                f"No processo de {topic}, o limite financeiro é {value}. O prazo de entrega é {days} dias corridos.",
                f"{org} — anexo de {topic}. A norma de {topic} entrou em vigor em {date}. O item abrangido é {item}. "
                f"O registro de transição de {topic} lista {previous} dias corridos como prazo de entrega. "
                "O registro de transição está ativo e não há data de encerramento nem indicação de prevalência neste anexo.",
            ]
            corpus.extend({"document_id": did, "user_id": 1, "filename": filename, "page": page, "text": text}
                          for page, text in enumerate(pages, 1))
            questions = [
                ("factual", f"Quem aprova o protocolo {code}?", [1], [team]),
                ("contextual", "E qual é o teto?", [1], [value]),
                ("comparacao", f"Compare o prazo de entrega da norma de {topic} da {org} com o registro de transição.", [1, 2], [str(days), str(previous)]),
                ("data", f"Em que data a norma de {topic} da {org} começou a valer?", [2], [date]),
                ("valor", f"Quanto a {org} permite gastar no processo de {topic}?", [1], [value]),
                ("ausente", f"Na política de {topic} da {org}, {MISSING_QUESTIONS[i].lower()}", [], []),
                ("ambigua", f"Os dois registros ativos da {org} para {topic} concordam sobre quantos dias há para entrega?", [1, 2], [str(days), str(previous)]),
            ]
            for category, question, relevant, required in questions:
                history = ([{"role": "user", "content": f"Sobre {topic} da {org}, quais são as regras financeiras?"}]
                           if category == "contextual" else [])
                cases.append({"id": f"{split}-{i+1}-{category}", "split": split, "category": category,
                              "question": question, "history": history, "document_id": did,
                              "relevant": [(did, page) for page in relevant], "required": required})
    return corpus, cases
