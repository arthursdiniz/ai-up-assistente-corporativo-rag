# Verificação da evolução — 9 de setembro de 2026

## Resultado

Escopo local aprovado implementado: confiabilidade documental, inteligência contextual e usabilidade. Nenhuma conta existente foi redefinida. Nenhum documento original foi excluído. As alterações desta tarefa ainda não foram enviadas ao GitHub.

## Evidências

| Camada | Verificação | Resultado |
|---|---|---|
| Testes isolados | pytest com SQLite, arquivos temporários, mock/hash | 62 passaram |
| PostgreSQL real | Banco novo ai_up_test_20260909_212717_552512, cadeia completa de migrations + modelos + pytest | 62 passaram; modelos compatíveis |
| Dependências | pip check | Sem dependências quebradas |
| JavaScript | node --check nos arquivos JS | Sem erros sintáticos |
| Git | git diff --check | Sem erros de whitespace; avisos normais LF/CRLF |
| Backup | Manifesto SHA-256, dump, uploads e Chroma | Verificado |
| Restauração | Novo banco ai_up_restore_validation_20260909 e data/restore_validation_20260909 | Funcionou; cópia mantida para inspeção |
| Migração principal | Alembic 20260909_0003 | Aplicada |
| Reindexação | Nove documentos originais | Nove prontos, zero falhas |
| Tokenização real | 258 trechos após acrescentar o fixture de demonstração | Máximo 120 tokens, limite 120; consultas com finais distintos mantêm vetores distintos |
| Recuperação real | 20 casos sintéticos | 90% Hit@3; não é precisão textual geral |
| Geração real | Seis fixtures Ollama | 6/6 verificações controladas |

Aviso de testes: há uma depreciação emitida por Starlette/TestClient sobre httpx. Não impediu os testes e não foi feita atualização ampla de dependências por esse aviso.

## Fluxos verificados no navegador

- Login na conta de demonstração existente.
- Criação automática de conversa com documento selecionado.
- Pedido de resumo em dois tópicos e continuação “Qual é o prazo?” sobre férias.
- Citação abre o trecho correto; a página PDF original é renderizada como imagem com navegação.
- Biblioteca exibe metadados e progresso real: arquivo fictício demo_checklist.txt passou por Extraindo texto e terminou Pronto.
- Favorito e feedback positivo persistidos.
- Refazer manteve quatro mensagens na conversa de validação: nenhuma pergunta duplicada.
- Cancelamento durante Redigindo a resposta não acrescentou mensagens e recuperou a pergunta no campo de edição.
- Exportação HTML gerou C:\Users\arthu\Downloads\ai-up-conversa.html, com fontes e excertos. O evento de download do instrumento de automação expirou, mas o arquivo e o GET 200 foram confirmados.
- Layout verificado nas larguras de 1280 e 390 pixels, com histórico e saída acessíveis no menu móvel.
- Diagnóstico respondeu com banco, Ollama, OCR português, modelo em cache e disco disponíveis.
- Console da aba sem erros de JavaScript nas verificações realizadas.
- Rotas administrativas de qualidade, estatísticas e auditoria verificadas via HTTP autenticado. A criação de usuário e a troca de senha não foram executadas sobre contas reais; estão cobertas pelos testes isolados.

As skills de verificação orientaram a checagem UI → API → dados → resposta. A automação disponível foi o navegador integrado, pois agent-browser não estava instalado. A inspeção visual da skill PDF identificou um iframe em branco; a implementação passou a renderizar a página no servidor e a nova imagem foi conferida.

## Preservação

Backup anterior: data/backups/20260909T163732499396Z. A cópia restaurada contém quatro usuários, nove documentos, 14 conversas e 103 mensagens. Na conferência após os testes de interface, a base principal continha as quatro contas, os nove documentos originais mais um fixture, uma conversa adicional e quatro mensagens adicionais. Refazer/cancelar não aumentaram o total dessa conversa.

O banco de teste, a restauração e o backup foram mantidos. Uploads, índices, backups e restaurações estão ignorados no Git. Exportações podem conter dados sensíveis e devem ser guardadas com cuidado.

## Fronteiras

Citações podem estar incorretas e precisam de conferência. Resumos hierárquicos podem perder detalhes. O cancelamento é cooperativo; o modelo pode continuar ocupado até devolver controle. Não há validação humana independente concluída, avaliação de carga, servidor distribuído ou base compartilhada entre equipes. Consulte OPERACAO.md e AVALIACAO_IA.md.
