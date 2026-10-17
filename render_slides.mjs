import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [input, finalPath, skill, modules, python] = process.argv.slice(2).map(value => path.resolve(value));
process.env.RUNTIME_NODE_MODULES = modules;
const { Presentation, PresentationFile } = await import(pathToFileURL(path.join(modules, '@oai/artifact-tool/dist/artifact_tool.mjs')));
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')));
const data = JSON.parse(await fs.readFile(input, 'utf8'));
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const font = 'Arial Unicode MS';
presentation.theme.defaultFont = font;
function box(slide, text, x, y, width, height, size, bold = false, color = '#182737') {
  const shape = slide.shapes.add({ geometry: 'textbox', position: { left:x, top:y, width, height },
    fill:'none', line:{ fill:'none', width:0 } });
  shape.text = text;
  shape.text.style = { typeface:font, fontSize:size, bold, color };
  return shape;
}
const build = path.dirname(input);
const preview = path.join(build, 'slides-preview');
await fs.mkdir(preview, { recursive:true });
let tableOwners = [];
for (const [i, content] of data.entries()) {
  const slide = presentation.slides.add();
  slide.background.fill = '#FFFFFF';
  if (content.kind === 'cover') {
    box(slide, content.title, 76, 170, 1120, 240, 52, true);
    box(slide, content.text, 80, 475, 1100, 80, 26, false, '#526270');
  } else {
    box(slide, content.title, 72, 40, 1136, 100, 40, true);
    if (content.kind === 'table') {
      tableOwners.push(i+1);
      const values = [content.columns, ...content.rows];
      const t = slide.tables.add({ rows:values.length, columns:content.columns.length,
        left:72, top:158, width:1136, height:440, values });
      t.borders.assign({ style:'solid', fill:'#D9D9D9', width:1 });
      for (let r=0;r<values.length;r++) for (let c=0;c<content.columns.length;c++) {
        const cell=t.getCell(r,c);
        cell.fill = r===0 ? '#E5EDF2' : r%2===0 ? '#F5F7F9' : '#FFFFFF';
        cell.text.style={typeface:font,fontSize:23,bold:r===0,color:'#182737'};
      }
    } else if (content.kind === 'points') {
      // Each paragraph has a predictable frame; long points use additional vertical space.
      let y=160;
      const lineWidth=38;
      for (const text of content.points) {
        const units=[...text].reduce((n,c)=>n+(c.charCodeAt(0)>255?1:.52),0);
        const height=Math.max(54, Math.ceil(units/lineWidth)*36+18);
        if(y+height>654) throw new Error('Content requires another slide: '+content.title);
        box(slide,text,78,y,1118,height,28);
        y+=height+10;
      }
    } else {
      box(slide, content.text, 76, 156, 1120, 492, 26);
    }
    box(slide, String(i+1), 1140, 666, 62, 26, 16, false, '#6B7780');
  }
  slide.speakerNotes.text=content.notes||'';
  const png=await presentation.export({slide,format:'png',scale:1});
  await fs.writeFile(path.join(preview,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(presentation)).save(candidate);
// The finalizer intentionally refuses to overwrite an older final result.
const stamp=Date.now();
const attempt=path.join(path.dirname(finalPath),'.validated-'+stamp+'.pptx');
await finalizePresentation({workspaceDir:path.resolve(path.dirname(build)),candidatePath:candidate,finalPath:attempt,
  pythonExecutable:python,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
  explicitTotalSlideCount:data.length,requiredNativeTableOwnerSlides:tableOwners,
  fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
  receiptPath:path.join(build,'presentation-check-'+stamp+'.json')});
await fs.copyFile(attempt,finalPath);
await fs.unlink(attempt);
