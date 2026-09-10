# Demonstração do AI-Up — 5 minutos

## Antes

Abra o Ollama e inicie .\scripts\start_ai_up.ps1. Entre com uma conta local existente, confira Diagnóstico e conta e o documento regulamento_empresa_demo.pdf na biblioteca. Se já existe, não envie novamente: duplicatas agora são detectadas. Evite documentos pessoais na projeção.

## 0:00–0:40 — problema e privacidade

“Consultar regulamentos e contratos consome tempo. O AI-Up transforma documentos locais em respostas com trechos que podem ser conferidos.” Mostre a biblioteca, tipos, estado Pronto e categorias.

## 0:40–1:40 — tarefa útil e evidência

Clique Consultar com IA no regulamento. Peça: “Resuma as regras de férias em dois tópicos.” Mostre a resposta progressiva, clique em [1] e abra a página original. Diferencie fonte verificável de garantia de acerto.

## 1:40–2:20 — conversa contextual

Pergunte: “Qual é o prazo?” Demonstre que a referência continua sendo férias. O resultado esperado é antecedência de 30 dias corridos. Uma pergunta com um assunto explicitamente nomeado inicia outra busca; a seleção documental continua sendo o limite de acesso.

## 2:20–3:10 — transformar informação em trabalho

Peça: “Monte um checklist das obrigações do regulamento, incluindo prazos.” Mostre citações de páginas diferentes. Use exportação HTML para um relatório imprimível com fontes. Para comparar versões, selecione as duas explicitamente.

## 3:10–3:45 — informação ausente

Pergunte: “Qual é o valor do vale-alimentação?” A resposta esperada é a recusa. Explique: a busca pode localizar um trecho parecido, mas isso não autoriza inventar o benefício. Essa distinção foi testada separadamente.

## 3:45–4:20 — usabilidade

Mostre favoritos, busca no histórico, feedback com motivo e diagnóstico. Refazer substitui apenas a última resposta; Parar impede salvar a geração cancelada. A pergunta pode ser recuperada para nova tentativa.

## 4:20–5:00 — resultados e limites

Mostre docs/AVALIACAO_IA.md: 90% Hit@3 em 20 casos sintéticos, 6/6 verificações controladas do modelo real, testes de isolamento e migração PostgreSQL. Não anuncie “90% de precisão geral da IA”. Termine com os limites: heurísticas de contexto, erros de OCR, perda de detalhes na condensação e necessidade de avaliação humana em documentos inéditos.

## Perguntas prováveis

- **Pode inventar?** Sim. Prompt, seleção de evidências e avisos reduzem o risco, mas é preciso conferir fontes.
- **Por que duas bases?** PostgreSQL guarda contas, conversas, jobs e evidências; Chroma guarda os vetores de busca.
- **É aprendizado automático com feedback?** Não. O feedback é registrado para diagnóstico e melhoria; não treina o modelo automaticamente.
- **Pronto para uma empresa inteira?** Este escopo é local e monoprocesso. Equipes, governança, autenticação organizacional, filas distribuídas e testes de carga são próximos projetos.
- **Como recuperar dados?** Backup verificável e restauração em destino novo. Nunca redefinir contas ou apagar o índice antigo antes de preparar o novo.
