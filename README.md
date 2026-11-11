# Guilherme Molina — Portfólio

Design digital, sites e dashboards em um portfólio responsivo, com seis projetos e demonstração interativa de analytics.

**[Abrir o site](https://guilherme-molina-portfolio.guilhermemolinasolan.chatgpt.site)** · **[Olist Analytics](https://github.com/MolinaGG/olist-ecommerce-analytics)** · **[LinkedIn](https://www.linkedin.com/in/guilhermesolano)**

O site hospedado está privado para revisão do proprietário. Publicar este código no GitHub não altera essa configuração.

## Projetos

- Kart Lokos: oito peças selecionadas entre 22 explorações visuais.
- Vértice Motors: projeto demonstrativo de uma revenda fictícia.
- Olist Analytics: dashboard com filtros, quatro visões e exportação CSV.
- Toniolo Kart: apresentação visual para canal.
- O cofre não basta: capa editorial pessoal sobre Binance, sem vínculo comercial.
- Data & Analytics: apresentação profissional para LinkedIn.

## Executar localmente

Requer Python 3 para servir os arquivos. Não há instalação nem etapa de compilação.

```bash
python -m http.server 8000
```

Abra http://localhost:8000. O dashboard fica em http://localhost:8000/olist/. Servir por HTTP é necessário para carregar o JSON de dados; abrir o HTML diretamente como arquivo não é suficiente.

## Organização

`index.html`, `styles.css` e `app.js` contêm o portfólio. `assets/` reúne as imagens otimizadas e `olist/` contém o dashboard independente. O modelo Power BI, as fontes e o processo de reconstrução dos dados estão no [repositório Olist](https://github.com/MolinaGG/olist-ecommerce-analytics).

O site usa HTML, CSS e JavaScript sem dependências de execução. As fontes do Google Fonts são opcionais; há alternativas locais de tipografia.

## Validação

Filtros dos projetos, navegação móvel, galerias, teclado e carregamento de imagens foram verificados em navegador. O dashboard teve os indicadores confrontados com os CSVs e o modelo Power BI. Para testes dos cálculos, consulte o repositório Olist.

## Créditos e contexto

Criação assistida por IA identificada nos projetos aplicáveis. As cenas do Kart Lokos são ilustrativas. Marcas e nomes de terceiros identificam os assuntos ou projetos apresentados; não implicam parceria ou endosso.

As imagens e marcas não recebem uma licença geral de reutilização por este repositório. A configuração do serviço de hospedagem e os arquivos temporários do desenvolvimento não estão incluídos.
