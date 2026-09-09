# Diagnóstico da inteligência do AI-Up

## Problema observado

A versão inicial funcionava bem para perguntas literais e objetivas, mas tinha três fragilidades:

1. tratava cada pergunta quase isoladamente, então pronomes como “ela” e continuações como “o que mais?” perdiam o assunto da conversa;
2. usava apenas similaridade vetorial, o que podia enfraquecer códigos, siglas, números e nomes exatos;
3. qualquer trecho acima de um único limiar era enviado ao modelo, inclusive correspondências apenas vagamente relacionadas.

O efeito visível era uma recusa prematura em perguntas abertas ou, no extremo oposto, uma fonte pouco convincente para assuntos ausentes.

## Causas técnicas

- ausência de classificação da tarefa antes da recuperação;
- ausência de reescrita contextual da consulta;
- recuperação exclusivamente semântica;
- falta de uma política específica para evidência somente semântica;
- fontes sem excerto verificável;
- interface sem estados de progresso, nova tentativa e avaliação da resposta.

## Correções implementadas

- classificação local de perguntas factuais, resumos, explicações, comparações, extrações, linhas do tempo, riscos, localização e continuações;
- uso das seis mensagens recentes somente quando a pergunta realmente depende do histórico;
- mudança explícita de assunto sem contaminação da conversa anterior;
- busca híbrida: embeddings multilíngues + BM25 local;
- fusão ponderada, remoção de duplicatas e reranqueamento por termos, números e diversidade de página/planilha;
- política de suficiência: correspondência lexical aceita pelo limiar geral; correspondência apenas semântica exige similaridade mais forte;
- prompt do modelo com tarefa, histórico selecionado, contexto não confiável delimitado e regra contra injeção de prompt;
- fontes persistidas com documento, página/planilha, relevância e excerto;
- feedback positivo/negativo por mensagem para evolução futura.

## Resultado

No corpus local versionado, a nova recuperação alcançou 100% de Hit@3, 100% de acerto da primeira fonte e 100% de resolução das perguntas contextuais. A precisão média das três fontes subiu de 51,28% para 74,36%. Consulte [AVALIACAO_IA.md](AVALIACAO_IA.md) para método e limitações.
