# Protocolo de avaliação humana do AI-Up

**Estado: PENDENTE DE VALIDAÇÃO HUMANA.** Este protocolo complementa a avaliação automatizada. Seu objetivo é medir se uma pessoa consegue verificar as respostas nos documentos e reconhecer omissões, contradições e afirmações sem apoio.

1. Prepare 24 perguntas inéditas sobre documentos sintéticos ou autorizados. Distribua quatro perguntas em cada grupo: factual, contextual, comparação/contradição, datas, valores e informação ausente. Inclua pelo menos duas perguntas com referente ambíguo e anote se o comportamento esperado é esclarecer ou comparar as versões. Varie formatos e redação. Separe os documentos e as perguntas das fixtures automatizadas.
2. Antes de gerar respostas, congele a lista e o gabarito. Registre versão dos documentos, trechos, fatos obrigatórios, respostas aceitáveis, fatos ausentes, conflitos e o escopo autorizado. Para perguntas contextuais, fixe também o histórico enviado. A pessoa que redige as perguntas deve evitar reutilizar a redação dos trechos como regra geral.
3. Rode o fluxo completo com a mesma ingestão e configuração de recuperação, em ambiente isolado. Preserve a pergunta, a saída, o estado de erro e as fontes realmente exibidas. Compare apenas condições declaradas. Se comparar dois modelos, embaralhe a ordem por pergunta com uma semente registrada e mantenha a correspondência entre código e modelo com uma pessoa que não atribui notas.
4. Dois avaliadores analisam as saídas independentemente. Para cada afirmação verificável, registrem se é sustentada, contradita ou sem apoio. Confiram número, versão, página ou seção, conteúdo do trecho e acesso no escopo experimental. Usem o [CSV de registro](AVALIACAO_HUMANA_MODELO.csv) com uma linha por pergunta, resposta e avaliador.
5. Antes de revelar as condições, relatem quantidade de avaliações válidas, distribuição de notas por dimensão e por grupo, percentuais de afirmações sustentadas e citações corretas com denominadores, concordância entre avaliadores e exemplos de divergência. Relatem erros de execução separadamente. Registrem adjudicação em linhas separadas ou em ata. Com dois avaliadores e amostra suficiente, acrescentem kappa ponderado por dimensão e sempre informem o tamanho da amostra. Não somem as dimensões em uma nota única sem pré-definir a regra.

Use `NA` quando uma dimensão não se aplicar. Uma recusa correta para informação ausente recebe nota 2 em reconhecimento de ausência. Qualidade das evidências recebe `NA` nessa recusa quando não se espera uma citação. Para avaliação em português, registre no campo de observações erros linguísticos que alteram significado ou prejudicam a leitura. Preserve as notas individuais antes da adjudicação.

| Critério | 0 | 1 | 2 |
|---|---|---|---|
| Correção factual | Algum fato central contradiz o gabarito | Erro secundário ou formulação imprecisa | Todos os fatos apresentados estão corretos |
| Fidelidade ao documento | Fato central sem apoio no trecho ou documento | Apoio apenas parcial | Todas as afirmações verificáveis têm apoio no corpus autorizado |
| Completude | Resposta omite a maior parte da informação necessária | Entrega parte do pedido | Cobre todos os fatos exigidos ou explicita o que falta |
| Relevância | Responde a outra pergunta | Responde com desvios ou excesso substancial | Responde ao pedido de forma direta |
| Qualidade das evidências | Fonte ausente, inválida ou contrária a fato central | Fontes válidas, com cobertura incompleta | Citações localizáveis sustentam todas as afirmações necessárias |
| Reconhecimento de ausência | Inventa, escolhe versão sem apoio ou recusa quando havia evidência clara | Sinaliza incerteza sem localizar o que falta | Identifica o que não consta, pede esclarecimento ou expõe o conflito, conforme gabarito |

Armazene o gabarito, a chave de cegamento e as respostas em pasta controlada. O CSV versionado é um formulário vazio. Publique resultados agregados e exemplos sintéticos. Registre versão do código, dos documentos e do modelo, configuração e critérios de inclusão ou exclusão.
