const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
for(const page of ['index.html','pt.html','creative.html','olist/index.html']) {
  test(`${page}: internal links resolve to existing pages and anchors`,()=>{
    const html=fs.readFileSync(path.join(root,page),'utf8');
    for(const [,href] of html.matchAll(/<a\b[^>]*\bhref="([^"]+)"/g)) {
      const url=new URL(href,`http://portfolio.local/${page}`);
      if(url.origin!=='http://portfolio.local')continue;
      let target=path.join(root,decodeURIComponent(url.pathname));
      if(fs.existsSync(target)&&fs.statSync(target).isDirectory())target=path.join(target,'index.html');
      assert.ok(fs.existsSync(target),`${page}: ${href} target missing`);
      if(url.hash){
        const destination=fs.readFileSync(target,'utf8');
        const ids=[...destination.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
        assert.ok(ids.includes(decodeURIComponent(url.hash.slice(1))),`${page}: ${href} anchor missing`);
      }
    }
  });
}
