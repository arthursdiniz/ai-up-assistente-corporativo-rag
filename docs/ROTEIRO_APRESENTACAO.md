# Demonstração do AI-Up

## Roteiro principal — Auditor documental

Na raiz do projeto, use uma instância descartável. Inicie com `--ollama` se quiser mostrar a resposta real e o modelo local estiver disponível. Sem essa opção, o chat usa mock e o Auditor continua funcional.

```powershell
.venv\Scripts\python.exe -B scripts/demo_auditor.py --automatic --ollama
```

1. Acesse `http://127.0.0.1:8013` e entre com a conta sintética impressa no PowerShell. Abra **Documentos**, envie `evals/auditor_demo/v1/reembolso-viagens.txt` e `evals/auditor_demo/circular-reembolso.txt`, e aguarde o estado **Pronto**. Use `--sample` ao iniciar para ter esses arquivos já preparados.
2. Abra **Auditor**. Aguarde a auditoria automática ou clique **Analisar** com `reembolso-viagens.txt` selecionado. Abra o alerta de R$ 150 e R$ 200. Confira o mesmo departamento, as datas e os dois links **Abrir fonte original**. Registre **Confirmado**, com justificativa curta.
3. Envie `evals/auditor_demo/excecao-viagem.txt`. Explique que R$ 350 se refere a um caso específico. Esse arquivo não deve acrescentar uma contradição à lista.
4. Envie `evals/auditor_demo/v2/reembolso-viagens.txt`, com o mesmo nome. Aguarde **Pronto**. Mostre **Alteração relevante** no limite e a obrigação de guardar o recibo. O alerta de R$ 150 × R$ 200 passa a histórico. Marque **Incluir alertas históricos**, abra-o e registre **Resolvido** com justificativa.
5. Abra o arquivo v2, clique **Consultar com IA** e pergunte “Qual é o limite de reembolso de viagens?”. Na geração real, confira `R$ 200,00` e a fonte. Em uma janela privada, entre com `externo@demo.aiup.local`, usando a mesma senha sintética exibida no terminal. A Central fica vazia e o link direto de uma fonte da primeira conta não carrega seu conteúdo. A suíte `pytest tests/test_auditor.py -q` também verifica `404` em rotas de detalhe e revogação de equipe.
6. Rode `scripts/evaluate_auditor.py` com o Python do ambiente virtual. Mostre o conjunto reservado e o de estresse lado a lado, incluindo os falsos negativos. Encerre com o protocolo humano cego. [Métricas e limites](AVALIACAO_AUDITOR.md)

## Roteiro complementar — Chat RAG em 5 minutos

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
- **Pronto para uma empresa inteira?** Este escopo é local e monoprocesso, com equipes e autenticação organizacional. Filas distribuídas e carga prolongada em PostgreSQL exigem validação adicional.
- **Como recuperar dados?** Backup verificável e restauração em destino novo. Nunca redefinir contas ou apagar o índice antigo antes de preparar o novo.
