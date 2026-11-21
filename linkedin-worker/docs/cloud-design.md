# Worker contínuo em nuvem

Pedido autorizado: migrar operação para GitHub Actions, manter 3 posts/dia e gerar novos após os 90 iniciais. A API OpenAI será opcional e só usada com chave Platform própria e geração explicitamente habilitada. Token de sessão Codex não será extraído/reutilizado. Credenciais e custos ainda dependem da resposta do usuário.

## Decisões
- GitHub Actions diário 09:17 UTC (06:17 Brasília), manual_dispatch, concurrency sem cancelamento. Buffer mantém horários08:30/12:30/18:00 e fila10.
- Python existente preservado. Workflow em repositório público de portfólio, pasta linkedin-worker; nenhum segredo em commits.
- Estado durável em arquivo JSON via API GitHub contents, compare-and-swap SHA. Inclui catálogo, manifesto de imagens, journal e consumo de IA. Gravar intenção durável ANTES de mutações Buffer e chamadas IA; falhar fechado se persistência falhar. Não depender de cache/artifacts efêmeros.
- Migração importa diário atual dos10 agendados; reconcilia Buffer antes de qualquer envio. Um único workflow é proprietário da publicação. Não executar sincronização local paralela.
- Geração: Responses API com pesquisa web em fontes primárias, JSON validado, segunda revisão com pesquisa e verificação de fontes, comparação de temas e histórico. Imagens PNG locais pelo Pillow, publicadas por hash no GitHub antes de importar o lote.
- Uma tentativa de geração/dia e no máximo2 chamadas IA/dia; limites tokens, websearch e saldo mensal de chamadas. Sem tentativas automáticas após resposta incerta. Sem saldo/key/configuração, interromper geração e avisar no relatório do Actions. Novos posts somente após90 enviados e backlog baixo.
- Estilo: português direto, sem emojis, sem falsa experiência ou busca explícita de emprego. Alternar SQL, BI, projetos, decisões; exemplos didáticos identificados. CTA específico, sem engajamento artificial, comentários ou mensagens automáticas.
- Aprendizado editorial por métricas fornecidas CSV (impressões, comentários, compartilhamentos) opcionais, nunca inventadas. Relatório de melhores temas; sem métricas, rotação editorial.
- Falha de fonte/revisão: não publicar. Erro de publicação/rede: persistir incerteza e parar. Exibir resultados confirmados no job summary, notificação de falha pelo GitHub.

## Alternativas consideradas
n8n Community exige hospedar/manter servidor; n8n Cloud é pago. Actions reaproveita Python e dispensa servidor. A gratuidade depende das condições/cotas GitHub; IA pode consumir créditos pagos. Não há promessa de execução eterna nem de engajamento.

## Ativação
Arquitetura e workflow serão preparados e publicados se o conector permitir. Buffer secret no GitHub e API OpenAI/modelo/geração configurados pelo usuário via interface ou CLI autenticada; nunca copiar segredo em toolargs/chat. Executar primeiro validação, depois job real e verificar estado. Sem acesso à configuração dos secrets, entregar link direto e dependência precisa.
