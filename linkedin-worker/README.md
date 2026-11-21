# LinkedIn worker — Guilherme Molina Solano

Worker diário em GitHub Actions para manter três publicações por dia no LinkedIn, com fontes e imagens. Usa primeiro os 90 posts existentes e, após todos constarem como enviados, gera novos lotes pela API OpenAI. Os 10 agendamentos existentes são migrados pelo seed, sem reenviar.

## Arquitetura

```mermaid
flowchart TD
 A[GitHub Actions: diário 06h17 Brasília] --> B[Restaurar estado GitHub com SHA]
 B --> C[Conciliar fila e envios do Buffer]
 C --> D{90 enviados e backlog menor que6?}
 D -->|Não| I[Completar fila até 10]
 D -->|Sim| E[Reservar tentativa e quota no estado]
 E --> F[OpenAI: pesquisar fontes e escrever3posts]
 F --> G[OpenAI: revisar textos, fontes e cartões]
 G --> H[Pillow: gerar PNG e hospedar por hash]
 H --> I
 I --> J[Gravar intenção antes de cada envio]
 J --> K[Buffer: agendar e reler confirmação]
 K --> B
```

## Ativação

O workflow fica em `.github/workflows/linkedin-worker.yml`; código em `linkedin-worker/`. Em [Repository secrets](https://github.com/MolinaGG/guilherme-molina-portfolio/settings/secrets/actions), crie:

| Secret | Valor |
|---|---|
| BUFFER_API_KEY | Chave da sua conta Buffer já conectada ao LinkedIn |
| OPENAI_API_KEY | Chave criada na OpenAI Platform; nunca token de sessão do Codex |

O `GITHUB_TOKEN` é fornecido pelo próprio Actions, não precisa criar PAT. Não publique chaves em arquivos, commits, issues, screenshots ou chat.

Depois acesse [Actions / LinkedIn worker](https://github.com/MolinaGG/guilherme-molina-portfolio/actions/workflows/linkedin-worker.yml), clique **Run workflow**, branch **main**, e acompanhe o job **publish**. Push de código do worker, cron e execução manual testam antes de publicar. Commits de estado e imagens não acionam o workflow. Um job verde com `status: ok` e readback confirma a execução. `scheduled: 0` é normal se a fila estiver cheia. O estado persistente fica em `linkedin-worker/runtime/state.json`.

A recorrência é 09:17 UTC (06h17 Brasília), independente do seu PC. Buffer entrega08h30/12h30/18h. O horário do cron pode atrasar; a fila dá antecedência. GitHub pode desativar agendamentos públicos após 60 dias sem atividade; os commits de estado mantêm atividade durante operação normal, mas confira Actions após pausas longas.

## Configuração opcional por Repository variables

| Variável | Padrão | Finalidade |
|---|---|---|
| OPENAI_MODEL | gpt-5-mini | Modelo com Responses e web_search disponível na sua conta |
| MAX_MONTHLY_AI_CALLS |64| Teto de requisições IA por mês, entre 2 e 64 |
| ENABLE_LINKEDIN_GENERATION |true| false interrompe novos textos, preserva publicação de conteúdo pronto |
| LINKEDIN_WORKER_PAUSED |false| true impede novas execuções de publicação |

Para pausar imediatamente, desabilite o workflow ou configure `LINKEDIN_WORKER_PAUSED=true`. Posts já agendados no Buffer continuam; pause também o canal Buffer se quiser interromper entregas. Não execute `publisher.py sync --apply` local nem a antiga tarefa Codex em paralelo ao worker.

## Custos e limites

- Actions em runner Linux padrão de repositório público segue a gratuidade/cotas do GitHub. Não provisionamos servidor n8n.
- Buffer mantém limite de 10 posts na fila e suas próprias cotas de API. O worker consulta todos os posts não enviados e os enviados nos últimos 7 dias. Reserva cada requisição no histórico e para antes de ultrapassar 900 no mês, deixando margem para uso externo. Erro de cota interrompe a execução, sem retry de publicação.
- OpenAI Platform cobra uso da API e ferramentas. A assinatura ChatGPT/Codex não substitui essa cobrança. Durante os90 iniciais não há geração IA.
- No máximo1 tentativa de lote/dia e2 requisições de IA por tentativa, com saída limitada a 8000 tokens/requisição e até 6 chamadas de ferramenta por requisição. O teto64 é de chamadas, NÃO um teto financeiro. Configure também controles de gastos/créditos na Platform.
- Novos lotes só surgem com backlog abaixo de 6. Uma falha não dispara geração repetida no mesmo dia. Sem chave/modelo/créditos/fontes válidas, para e reporta em Actions.
- Execução contínua depende da disponibilidade dos serviços, créditos e políticas; não há promessa de funcionamento eterno ou engajamento garantido.

## Conteúdo e engajamento

Português direto, sem emojis, sem procura explícita de emprego, sem experiências inventadas. Temas de SQL, Power BI, Python, projetos e decisões de negócio. A pesquisa usa fontes primárias; a revisão independente precisa aprovar texto, pontos da imagem e referências. Isso reduz erros, mas não prova veracidade automaticamente.

O histórico recente orienta diversidade; não há automação de curtidas, comentários, mensagens ou conexões. O arquivo opcional `metrics.csv` recebe dados reais exportados/manualizados do LinkedIn, com `post_id,topic,impressions,comments,shares`. O worker agrega comentários+compartilhamentos/impressões e apresenta esses sinais ao gerador. Não há acesso automático a analytics contratado/conectado aqui, e amostras pequenas não provam qual assunto causou alcance.

## Estado e recuperação

- Compare-and-swap de SHA impede sobrescrever estado concorrente. O workflow serializa execuções.
- SQLite é reconstruído em diretório temporário a partir do estado durável. Antes de cada envio, `inflight` já deve estar no GitHub. Após resposta, fica `uncertain` até verificar ID/texto/horário/status.
- Timeout de escrita é ambíguo: nunca reenviar automaticamente. Próxima execução lê o estado e o Buffer. Se continuar incerto, inspecione os registros e a fila antes de resolver manualmente.
- Geração revisada é salva antes de hospedar imagens; uma execução seguinte retoma o lote por até 7 dias. Depois expira, evitando fontes antigas. Imagens usam nomes por hash e não sobrescrevem conteúdo existente.
- O estado ativo conserva os90 iniciais, os180 posts diários enviados mais recentes e todo conteúdo pendente, além de14 dias de auditoria de geração e3 meses de contadores. Versões anteriores continuam no histórico Git. Nenhum arquivo de imagem publicado é removido automaticamente.
- Repositório público: textos planejados e auditorias editoriais ficam públicos; as credenciais ficam somente em Actions secrets. Não inclua dados privados do empregador.
- Após uma interrupção superior a 7 dias, posts podem ter saído da janela de conciliação. Configure a variável `BUFFER_FULL_HISTORY=true`, execute uma recuperação manual e remova a variável após confirmar o estado. Isso consome mais requisições; não habilite permanentemente.
- Não apague `runtime/state.json` para consertar falhas: isso perderia intenções e contadores. `seed.json` serve apenas para primeira inicialização.

## Verificação

`python -m unittest discover -s tests -q` executa testes sem chamadas pagas ou posts reais. Integração real OpenAI só pode ser confirmada após configurar a chave. O cliente Buffer já agendou e releu 10 posts reais antes desta migração.

Fontes: [GitHub Actions](https://docs.github.com/en/actions/concepts/billing-and-usage), [agendamentos](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [Buffer API](https://developers.buffer.com/guides/posts-and-scheduling.html), [OpenAI autenticação](https://learn.chatgpt.com/docs/auth), [web search](https://developers.openai.com/api/docs/guides/tools-web-search).
