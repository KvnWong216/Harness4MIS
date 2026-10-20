import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [input,finalPath,skill,modules,python]=process.argv.slice(2).map(x=>path.resolve(x));
process.env.RUNTIME_NODE_MODULES=modules;
const {Presentation,PresentationFile}=await import(pathToFileURL(path.join(modules,'@oai/artifact-tool/dist/artifact_tool.mjs')));
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')));
const raw=JSON.parse(await fs.readFile(input,'utf8'));
const spec=Array.isArray(raw)?{slides:raw}:raw;
const slides=spec.slides;
const t={paper:'#F4F1E9',ink:'#142832',dark:'#102B3B',accent:'#B98054',muted:'#52646C',pale:'#E1E9E7',...spec.theme};
const cn='Arial Unicode MS',latin='Times New Roman';
const p=Presentation.create({slideSize:{width:1280,height:720}});p.theme.defaultFont=cn;
const build=path.dirname(input),preview=path.join(build,'slides-preview');await fs.mkdir(preview,{recursive:true});
const tables=[],diagrams=[],images=[];
function box(s,text,x,y,w,h,size=28,bold=false,color=t.ink){
 const sh=s.shapes.add({geometry:'textbox',name:'text-'+s.shapes.items.length,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text.style={typeface:cn,fontSize:size,bold,color,insets:0,verticalAlignment:'top',autoFit:'none',wrap:'square'};
 sh.text=String(text).split('\n').map(line=>({runs:(line.match(/[\u0000-\u024f]+|[^\u0000-\u024f]+/g)||['']).map(run=>({run,style:{typeface:/^[\u0000-\u024f]+$/.test(run)?latin:cn,fontSize:size+'px',bold,color}}))}));
 return sh;
}
function wrapSplit(text,width,size){
 const limit=Math.max(8,Math.floor(width/size)-1);
 return String(text).split('\n').map(line=>{
  const result=[];let current='',units=0;
  for(const ch of line){
   const next=ch.charCodeAt(0)>255?1:.55;
   if(units+next>limit&&!/^[，。！？：；、）】]$/.test(ch)){result.push(current);current='';units=0;}
   current+=ch;units+=next;
  }if(current)result.push(current);return result.join('\n');
 }).join('\n');
}
function panel(s,x,y,w,h,fill){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}});}
async function photo(s,src,x,y,w,h,focus='center'){
 if(!src)return;
 const file=path.isAbsolute(src)?src:path.resolve(build,src);const bytes=await fs.readFile(file);
 s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:({'.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.png':'image/png'})[path.extname(file).toLowerCase()]||'image/png',alt:spec.assetDescriptions?.[src]||'Illustrative scene',fit:'cover',...(focus==='right'?{crop:{left:0.4,top:0,right:0,bottom:0}}:{}),position:{left:x,top:y,width:w,height:h}});
}
function header(s,c,dark=false){box(s,c.title,64,60,1152,112,46,true,dark?'#F4F1E9':t.ink);}
function footer(s,i,dark=false,source=''){
 if(source)box(s,source,66,667,1080,28,16,false,dark?'#D5DFDE':t.muted);
 box(s,String(i+1).padStart(2,'0'),1160,666,52,28,18,false,dark?'#D5DFDE':t.muted);
}
function nativeTable(s,c,x=64,y=218,w=1152,h=376,dark=false){
 const values=[c.columns,...c.rows];const tab=s.tables.add({rows:values.length,columns:c.columns.length,left:x,top:y,width:w,height:h,values});
 const headerHeight=values.length===2?70:64;
 tab.rows[0].height=headerHeight;
 for(let r=1;r<values.length;r++)tab.rows[r].height=(h-headerHeight)/(values.length-1);
 tab.borders.assign({style:'solid',fill:dark?'#52666D':'#CDD5D0',width:1});
 for(let r=0;r<values.length;r++)for(let col=0;col<c.columns.length;col++){
  const cell=tab.getCell(r,col);cell.fill=r===0?(dark?'#294854':t.dark):r%2===0?(dark?'#203C46':'#E7ECE6'):(dark?'#19333E':t.paper);
  cell.text.style={typeface:cn,fontSize:c.tableSize||25,bold:r===0,verticalAlignment:'middle',color:dark||r===0?'#F4F1E9':t.ink};
  cell.value=String(values[r][col]).split('\n').map(line=>({runs:(line.match(/[\u0000-\u024f]+|[^\u0000-\u024f]+/g)||['']).map(run=>({run,style:{typeface:/^[\u0000-\u024f]+$/.test(run)?latin:cn,fontSize:(c.tableSize||25)+'px',bold:r===0,color:dark||r===0?'#F4F1E9':t.ink}}))}));
 }
 return tab;
}
for(const [i,c] of slides.entries()){
 const s=p.slides.add();s.background.fill=t.paper;
 const layout=c.layout||(c.kind==='cover'?'hero':c.kind==='table'?'table':c.kind==='text'?'text':i%3===0?'dark-points':'points');
 const dark=['route','dark-points','methods','closing'].includes(layout);
 if(dark)s.background.fill=t.dark;
 if(layout==='hero'){
  await photo(s,c.image,688,0,592,720,c.imageFocus||'center');
  if(!c.image)panel(s,0,0,1280,720,t.dark);
  panel(s,0,0,688,720,c.lightHero?t.paper:t.dark);
  const color=c.lightHero?t.ink:'#F8F6F0';
  box(s,c.kicker||'MIS303',66,58,660,48,22,true,color);
  box(s,c.title,64,196,596,230,c.titleSize||60,true,color);
  box(s,c.subtitle||c.text||'',68,452,574,126,28,false,color);
  box(s,c.byline||'',68,637,720,40,22,false,color);
  if(c.image)images.push(i+1);
 }else if(layout==='materials'){
  await photo(s,c.image,904,0,376,720);header(s,c);
  nativeTable(s,c,64,223,790,370,false);tables.push(i+1);if(c.image)images.push(i+1);
  footer(s,i,false,c.source);
 }else if(layout==='route'){
  header(s,c,true);const nodes=[];const stepW=250,gap=43;
  c.steps.forEach((step,k)=>{
   const x=65+k*(stepW+gap);
   box(s,String(k+1).padStart(2,'0'),x,210,200,90,72,false,t.accent);
   nodes.push(box(s,step.title,x,324,stepW,70,32,true,'#F4F1E9'));
   box(s,step.text,x,417,stepW,108,24,false,'#D5DFDE');
  });
  for(let k=0;k<nodes.length-1;k++)s.shapes.connect(nodes[k],nodes[k+1],{kind:'straight',fromSide:'right',toSide:'left',line:{fill:t.accent,width:2},tail:{type:'triangle',width:'sm',length:'sm'}});
  box(s,c.takeaway||'',66,583,1140,60,28,false,'#F4F1E9');diagrams.push(i+1);footer(s,i,true,c.source);
 }else if(layout==='quote'){
  panel(s,748,0,532,720,t.dark);box(s,c.title,64,60,640,104,46,true,t.ink);
  box(s,'人的设计选择',68,225,580,35,20,true,t.muted);
  box(s,c.quote,64,295,620,236,44,true,t.ink);
  box(s,c.attribution||'王誉功提出的要求',68,583,590,50,22,false,t.muted);
  box(s,'据此形成的补充提问',798,175,414,65,28,true,t.accent);
  box(s,c.addition,798,285,410,268,35,false,'#F4F1E9');
  footer(s,i,false,c.source);
 }else if(layout==='review'||layout==='split'){
  header(s,c);box(s,c.beforeLabel||(layout==='split'?'分析要点':'阅读原稿'),68,213,500,42,22,true,t.muted);box(s,c.afterLabel||(layout==='split'?'分析（续）':'继续追问'),680,213,520,42,22,true,t.muted);
  box(s,layout==='split'?wrapSplit(c.before,500,29):c.before,66,291,500,235,layout==='split'?29:37,false,t.ink);box(s,layout==='split'?wrapSplit(c.after,520,29):c.after,678,286,520,240,layout==='split'?29:39,true,t.dark);
  box(s,c.takeaway,68,576,1130,65,27,false,t.muted);footer(s,i,false,c.source);
 }else if(layout==='mechanism'){
  header(s,c);box(s,c.lead,66,220,430,178,37,true,t.ink);box(s,c.example,66,442,430,145,25,false,t.muted);
  nativeTable(s,c,552,220,662,370,false);tables.push(i+1);footer(s,i,false,c.source);
 }else if(layout==='methods'){
  await photo(s,c.image,0,0,1280,720);panel(s,0,0,720,720,t.dark);
  box(s,c.title,64,60,630,120,44,true,'#F4F1E9');
  (c.methods||[]).forEach((item,k)=>{
   box(s,String(k+1).padStart(2,'0'),68,231+k*123,68,54,36,false,t.accent);
   box(s,item.title,159,224+k*123,520,55,33,true,'#F4F1E9');
   box(s,item.text,159,277+k*123,494,66,23,false,'#D5DFDE');
  });if(c.image)images.push(i+1);footer(s,i,true,c.source);
 }else if(layout==='business'){
  header(s,c);box(s,c.lead||'',66,182,1150,57,29,false,t.muted);
  nativeTable(s,c,64,276,1152,320,false);tables.push(i+1);footer(s,i,false,c.source);
 }else if(layout==='insights'){
  header(s,c);(c.insights||[]).forEach((item,k)=>{
   const x=66+k*604;
   box(s,String(k+1).padStart(2,'0'),x,213,490,97,74,false,t.accent);
   box(s,item.title,x,337,520,90,38,true,t.ink);
   box(s,item.text,x,450,510,124,28,false,t.muted);
  });box(s,c.takeaway||'',66,605,1135,45,26,true,t.dark);footer(s,i,false,c.source);
 }else if(layout==='closing'){
  await photo(s,c.image,782,0,498,720,c.imageFocus||'center');header(s,c,true);
  (c.insights||[]).forEach((item,k)=>{
   box(s,'0'+(k+3),68,228+k*183,90,62,43,false,t.accent);
   box(s,item.title,176,225+k*183,562,71,34,true,'#F4F1E9');
   box(s,item.text,176,309+k*183,540,100,25,false,'#D5DFDE');
  });if(c.image)images.push(i+1);footer(s,i,true,c.source);
 }else if(layout==='table'){
  header(s,c);nativeTable(s,c,64,218,1152,390,false);tables.push(i+1);footer(s,i,false,c.source);
 }else if(layout==='text'){
  header(s,c);box(s,c.text||'',66,208,1144,416,26,false,t.ink);footer(s,i,false,c.source);
 }else{
  header(s,c,dark);
  let y=230;
  for(const text of c.points||[]){
   const units=[...text].reduce((n,ch)=>n+(ch.charCodeAt(0)>255?1:.52),0);const h=Math.max(70,Math.ceil(units/36)*38+20);
   if(y+h>642)throw Error('请精简该页或拆分到下一页：'+c.title);
   box(s,text,68,y,1100,h,31,false,dark?'#F4F1E9':t.ink);y+=h+18;
  }footer(s,i,dark,c.source);
 }
 s.speakerNotes.text=(c.notes||'')+(c.image?'\n\n画面来源：'+(c.imageCredit||spec.assetDescriptions?.[c.image]||'用户提供的PPT配图')+'。':'');
 await fs.writeFile(path.join(preview,`slide-${i+1}.png`),new Uint8Array(await(await p.export({slide:s,format:'png',scale:1})).arrayBuffer()));
 await fs.writeFile(path.join(preview,`slide-${i+1}.layout.json`),await(await s.export({format:'layout'})).text());
}
await fs.writeFile(path.join(build,'design-manifest.json'),JSON.stringify({layouts:slides.map(c=>c.layout||c.kind),nativeTables:tables,nativeDiagrams:diagrams,imageSlides:images},null,2));
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
const stamp=Date.now(),attempt=path.join(path.dirname(finalPath),'.validated-'+stamp+'.pptx');
await finalizePresentation({workspaceDir:path.resolve(path.dirname(build)),candidatePath:candidate,finalPath:attempt,pythonExecutable:python,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit',...tables.flatMap(n=>['--require-native-table-slide',String(n)])],
 explicitTotalSlideCount:slides.length,requiredNativeTableOwnerSlides:tables,fontPolicy:{basis:'design',families:[cn,latin],scriptFonts:{ea:cn}},verifyArtifactToolImport:true,
 receiptPath:path.join(build,'presentation-check-'+stamp+'.json')});
await fs.copyFile(attempt,finalPath);await fs.unlink(attempt);
console.log(JSON.stringify({finalPath,slides:slides.length,preview}));
