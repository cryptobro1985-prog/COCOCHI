import * as THREE from './vendor/three.module.js';
const host = document.getElementById('chickenScene');
try {
  const renderer = new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.5)); renderer.setClearColor(0,0);
  host.append(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36,1,.1,50); camera.position.set(0,1.8,7); camera.lookAt(0,1.1,0);
  scene.add(new THREE.HemisphereLight(0xe9dfff,0x34213f,3));
  const light = new THREE.DirectionalLight(0xffdb9c,4); light.position.set(3,5,4); scene.add(light);
  const rim = new THREE.PointLight(0xb45bff,30); rim.position.set(-3,2,-1); scene.add(rim);
  const chicken = new THREE.Group(); scene.add(chicken);
  const materials = {};
  for (const [key,color] of Object.entries({cream:0xffedcf,gold:0xffbf41,red:0xed536c,dark:0x21132e,pink:0xffb0b7,purple:0x8050e8})) materials[key]=new THREE.MeshStandardMaterial({color,roughness:.3,metalness:key==='gold'?.65:.05});
  function ball(x,y,z,sx,sy,sz,key,parent=chicken) { const m=new THREE.Mesh(new THREE.SphereGeometry(1,32,24),materials[key]); m.position.set(x,y,z); m.scale.set(sx,sy,sz); parent.add(m); return m; }
  ball(0,.65,0,.85,1,.68,'cream'); ball(0,1.6,.18,.67,.68,.62,'cream');
  const left=ball(-.82,.65,0,.22,.6,.42,'cream'); left.rotation.z=-.25;
  const right=ball(.82,.65,0,.22,.6,.42,'cream'); right.rotation.z=.25;
  for(const x of [-.26,.26]) { ball(x,1.78,.71,.16,.2,.075,'dark'); ball(x-.035,1.84,.77,.045,.06,.025,'cream'); ball(x*1.5,1.44,.66,.16,.08,.035,'pink'); ball(x,-.32,.18,.27,.12,.4,'gold'); }
  const beak=new THREE.Mesh(new THREE.ConeGeometry(.2,.42,4),materials.gold); beak.rotation.x=Math.PI/2;beak.position.set(0,1.48,.88);chicken.add(beak);
  ball(0,1.15,.69,.11,.2,.1,'red');
  for(const [x,y] of [[-.22,2.2],[0,2.32],[.22,2.2]])ball(x,y,.12,.16,.29,.16,'red');
  const crown=new THREE.Mesh(new THREE.TorusGeometry(.48,.07,12,48),materials.gold); crown.rotation.x=Math.PI/2;crown.position.set(0,2.06,.12);chicken.add(crown);
  const podium=new THREE.Mesh(new THREE.CylinderGeometry(1.25,1.45,.2,64),materials.purple);podium.position.y=-.55;scene.add(podium);
  const ring=new THREE.Mesh(new THREE.TorusGeometry(1.28,.035,12,64),materials.gold);ring.rotation.x=Math.PI/2;ring.position.y=-.43;scene.add(ring);
  function outfit(name) {
    materials.cream.color.set(name==='Cosmic'?0xc7a2ff:name==='Angel'?0xf7faff:name==='Street Gold'?0xffcf78:0xffedcf);
    materials.purple.color.set(name==='Cosmic'?0x3276d2:name==='Angel'?0x9ebee8:0x8050e8);
    crown.visible=name!=='Street Gold';
  }
  outfit(window.cocochiAppearance || 'Royal Neon');
  window.addEventListener('cocochi-state',e=>outfit(e.detail.outfit));
  function resize() { const w=host.clientWidth,h=host.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix(); }
  new ResizeObserver(resize).observe(host);resize();
  let visible=true;new IntersectionObserver(entries=>visible=entries[0].isIntersecting).observe(host);
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let angle=0;host.addEventListener('pointermove',e=>{angle=(e.offsetX/host.clientWidth-.5)*.6});
  function animate(t) { requestAnimationFrame(animate);if(!visible||document.hidden)return;chicken.rotation.y=angle;chicken.position.y=reduced?0:Math.sin(t*.002)*.045;left.rotation.z=-.25+(reduced?0:Math.sin(t*.003)*.05);right.rotation.z=-left.rotation.z;renderer.render(scene,camera); }
  animate(0);host.classList.add('ready');
} catch (_) { host.remove(); } // Existing artwork remains as the WebGL fallback.
