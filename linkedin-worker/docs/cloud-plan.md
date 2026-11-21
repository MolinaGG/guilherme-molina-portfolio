# Plano do worker em nuvem

Objetivo: publicação contínua com conteúdo novo, pesquisa e histórico durável. Spec: cloud-design.md.

- [ ] Persistência GitHub CAS, callback de journal antes de cada mutação e testes de perda de estado/conflitos.
- [ ] Gerador OpenAI com pesquisa + revisão + evidências, validação de diversidade e testes de respostas inválidas/fontes ausentes.
- [ ] Worker: restauração de estado, reconciliação, orçamento persistente antes da geração, renderização e hospedagem, import, sync.
- [ ] Workflow cron/manual, resumo, segredos, configuração e guia de implantação. Métricas opcionais sem promessa de engajamento.
- [ ] Testes integrados, revisão independente, publicação dos arquivos permitidos e relato de ativação real.

Revisão: timeout após write; persistência indisponível; execução duplicada; IA inválida ou semfontes; limite de chamadas; catálogo longo; ativos publicamente inacessíveis.
