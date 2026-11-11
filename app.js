'use strict';
const projects = {
  kart: { title:'Kart Lokos', category:'DESIGN / SOCIAL MEDIA', summary:'Uma série de explorações visuais para comunicar a experiência do kart amador. A seleção reúne oito peças entre 22 caminhos criativos, conectados pelo vermelho, preto e branco. Do visual cinematográfico ao editorial, cada peça explora uma forma de convidar o público para o universo da pista.', tags:['Direção visual','Criativos para redes','Criação assistida por IA'], note:'As cenas foram criadas com IA e são ilustrativas. Não representam registros documentais de pilotos ou etapas. As peças são explorações de linguagem, sem resultados de campanha comprovados.', images:[['kart-01','Cinemático noturno'],['kart-02','Editorial suíço'],['kart-06','Desenho técnico'],['kart-04','História em quadrinhos'],['kart-09','Miniatura isométrica'],['kart-14','Troféu como protagonista'],['kart-15','Minimalismo'],['kart-22','Tipografia brutalista']] },
  vertice: { title:'Vértice Motors', category:'SITE / PROJETO DEMONSTRATIVO', summary:'Projeto de uma revenda fictícia com experiência visual cinematográfica, catálogo de veículos, filtros, favoritos, comparação e painel administrativo. O desenvolvimento combina interface responsiva, movimento e organização de informações para explorar a jornada de quem procura um automóvel.', tags:['Design de interface','Desenvolvimento web','Catálogo e administração'], note:'Projeto demonstrativo: loja, veículos e condições não são uma oferta comercial real. A imagem exibida integra os materiais ilustrativos do projeto; a composição do cartão no portfólio não é uma captura da interface. Imagens de veículos geradas por IA.', images:[['vertice','Material visual do projeto Vértice Motors']], link:'https://github.com/MolinaGG/vertice-motors', linkLabel:'Explorar o projeto no GitHub ↗' },
  olist: { title:'Olist Analytics', category:'DADOS / DASHBOARD INTERATIVO', summary:'Estudo de análise de e-commerce com dados públicos da Olist, estruturado em três frentes: logística, qualidade de fornecedores e saúde financeira. O projeto conecta modelagem e consultas SQL a um dashboard em Power BI para explorar as informações do negócio.', tags:['MySQL','Power BI','DAX','Análise de negócio'], note:'Projeto de estudo com base pública, sem vínculo comercial com a Olist. A demonstração interativa usa os CSVs originais, com filtros e indicadores recalculados por pedido. A galeria combina a nova versão web e uma captura histórica da análise de logística. Os indicadores não são resultados gerados para um cliente.', images:[['olist','Visão executiva do dashboard'],['olist-logistica','Análise de eficiência logística']], link:'olist/', linkLabel:'Explorar o dashboard interativo ↗' },
  toniolo: { title:'Toniolo Kart', category:'DESIGN / CAPA DE CANAL', summary:'Uma composição para conectar a identidade do piloto ao conteúdo esportivo do canal. Retrato, ação em pista, rastros vermelhos e tipografia inclinada constroem uma presença visual marcada por energia e movimento.', tags:['Composição visual','Capa de canal','Universo esportivo'], note:'Peça fornecida para esta seleção do portfólio. A apresentação não atribui resultados de audiência ou desempenho comercial ao trabalho.', images:[['toniolo','Capa Toniolo Kart com retrato e piloto em ação']] },
  binance: { title:'O cofre não basta', category:'CAPA / CONTEÚDO EDITORIAL PESSOAL', summary:'Capa editorial pessoal sobre os limites da segurança em criptoativos. A metáfora do cofre e os elementos digitais traduzem o assunto em uma composição de alto contraste, com o amarelo como ponto de atenção e hierarquia tipográfica para destacar a mensagem.', tags:['Capa editorial','Composição','Finanças e tecnologia'], note:'Conteúdo pessoal. Não é uma campanha oficial, contratação ou parceria com a Binance. A marca aparece como assunto do conteúdo.', images:[['binance','Binance: o cofre não basta — Os limites da segurança cripto']] },
  linkedin: { title:'Data & Analytics', category:'DESIGN / MARCA PESSOAL', summary:'Capa profissional criada para minha presença no LinkedIn. Cubos, fluxos e linhas visuais remetem à organização e ao movimento dos dados. Nome, área de atuação e tecnologias são distribuídos para dar clareza à apresentação em um formato horizontal.', tags:['Capa de LinkedIn','Apresentação profissional','Dados e tecnologia'], note:'Projeto de apresentação pessoal. A arte está apresentada no formato original de capa.', images:[['linkedin','Capa profissional Guilherme Molina — Data & Analytics Engineer']] }
};
const dialog = document.querySelector('#project-dialog');
let selectedProject, selectedImage = 0;
function renderImage(){
  const [file,alt]=selectedProject.images[selectedImage];
  const image=document.querySelector('#gallery-image'); image.src=`assets/${file}.webp`;image.alt=alt;
  document.querySelector('#gallery-count').textContent=`${String(selectedImage+1).padStart(2,'0')} / ${String(selectedProject.images.length).padStart(2,'0')}`;
  document.querySelectorAll('#gallery-thumbs button').forEach((button,i)=>{button.classList.toggle('active',i===selectedImage);button.setAttribute('aria-pressed',String(i===selectedImage));});
  document.querySelector('#gallery-prev').disabled=selectedImage===0;
  document.querySelector('#gallery-next').disabled=selectedImage===selectedProject.images.length-1;
}
document.querySelectorAll('[data-project]').forEach(button=>button.addEventListener('click',()=>{
  selectedProject=projects[button.dataset.project];selectedImage=0;
  document.querySelector('#dialog-title').textContent=selectedProject.title;
  document.querySelector('#dialog-category').textContent=selectedProject.category;
  document.querySelector('#dialog-summary').textContent=selectedProject.summary;
  document.querySelector('#dialog-note').textContent=selectedProject.note;
  const tags=document.querySelector('#dialog-tags');tags.replaceChildren(...selectedProject.tags.map(t=>{const el=document.createElement('span');el.textContent=t;return el;}));
  const link=document.querySelector('#dialog-link');link.hidden=!selectedProject.link; if(selectedProject.link){link.href=selectedProject.link;link.textContent=selectedProject.linkLabel;}else{link.removeAttribute('href');link.textContent='';}
  const thumbs=document.querySelector('#gallery-thumbs');thumbs.replaceChildren(...selectedProject.images.map(([file,alt],i)=>{const b=document.createElement('button');b.setAttribute('aria-label',`Ver ${alt}`);const img=document.createElement('img');img.src=`assets/${file}.webp`;img.alt='';b.append(img);b.addEventListener('click',()=>{selectedImage=i;renderImage();});return b;}));
  thumbs.hidden=selectedProject.images.length===1;document.querySelector('.gallery-controls').hidden=selectedProject.images.length===1;
  renderImage();dialog.showModal();dialog.scrollTop=0;document.body.classList.add('dialog-open');
}));
document.querySelector('.close-dialog').addEventListener('click',()=>dialog.close());
dialog.addEventListener('close',()=>document.body.classList.remove('dialog-open'));
dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
function moveImage(delta){if(!selectedProject)return;const next=selectedImage+delta;if(next>=0&&next<selectedProject.images.length){selectedImage=next;renderImage();}}
document.querySelector('#gallery-prev').addEventListener('click',()=>moveImage(-1));
document.querySelector('#gallery-next').addEventListener('click',()=>moveImage(1));
dialog.addEventListener('keydown',e=>{if(e.key==='ArrowRight'){e.preventDefault();moveImage(1);}if(e.key==='ArrowLeft'){e.preventDefault();moveImage(-1);}});
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('[data-filter]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
  let count=0;document.querySelectorAll('.project').forEach(card=>{card.hidden=button.dataset.filter!=='todos'&&card.dataset.category!==button.dataset.filter;if(!card.hidden)count++;});
  document.querySelector('#filter-status').textContent=`${count} ${count===1?'projeto':'projetos'}`;
}));
const menuButton=document.querySelector('.menu-toggle'),nav=document.querySelector('#navigation');
menuButton.addEventListener('click',()=>{const open=nav.classList.toggle('open');menuButton.setAttribute('aria-expanded',String(open));});
nav.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{nav.classList.remove('open');menuButton.setAttribute('aria-expanded','false');}));
document.addEventListener('keydown',e=>{if(e.key==='Escape'){nav.classList.remove('open');menuButton.setAttribute('aria-expanded','false');}});
document.querySelector('#year').textContent=new Date().getFullYear();
