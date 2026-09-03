//-------------------------------------------------------------------------------
// Global változók
let canvas = null;
let currentSessionId = null;
let originalWidth = 0;
let originalHeight = 0;
let originalImage = null;

let objects = {};
let activeLayerId = 'original';
let objectCounter = 0;
let inpaintedBackgroundBase64 = null;
let lastUsedPrompt = '-';

// Eszköz állapotok
let isLassoMode = false;
let isPanningMode = false;
let isBrushMode = false;

// Lasszó & Pásztázás változók
let lassoPoints = [];
let lassoPolyline = null;
let isMouseDown = false;
let panLastX = 0;
let panLastY = 0;

// DOM Elemek
const imageInput = document.getElementById('imageInput');
const btnDrawLasso = document.getElementById('btnDrawLasso');
const btnRefineMask = document.getElementById('btnRefineMask');
const btnBrushAdd = document.getElementById('btnBrushAdd');
const btnBrushSub = document.getElementById('btnBrushSub');
const brushSizeInput = document.getElementById('brushSize');
const btnApplyBrush = document.getElementById('btnApplyBrush');
const btnInpaintBackground = document.getElementById('btnInpaintBackground');
const statusMessage = document.getElementById('statusMessage');
const canvasContainer = document.getElementById('canvasContainer');
const dynamicObjectLayers = document.getElementById('dynamicObjectLayers');
const layerList = document.getElementById('layerList');
//-------------------------------------------------------------------------------

// INICIALIZÁLÁS (Minden gombot itt kötünk be!)
function initApp() {
    canvas = new fabric.Canvas('mainCanvas', {
        width: canvasContainer.clientWidth,
        height: canvasContainer.clientHeight,
        selection: false
    });
    window.addEventListener('resize', resizeCanvas);

    // Vászon események
    canvas.on('mouse:down', onMouseDown);
    canvas.on('mouse:move', onMouseMove);
    canvas.on('mouse:up', onMouseUp);
    canvas.on('mouse:wheel', onMouseWheel);

    // Felső eszköztár
    document.getElementById('btnToolHome').addEventListener('click', fitImageToScreen);
    document.getElementById('btnToolPan').addEventListener('click', togglePanMode);
    document.getElementById('btnToolZoomIn').addEventListener('click', () => zoomCanvas(1.1));
    document.getElementById('btnToolZoomOut').addEventListener('click', () => zoomCanvas(0.9));

    // Rétegkezelő (Eredeti és Háttér)
    document.getElementById('layerOriginal').addEventListener('click', () => switchLayer('original'));
    document.getElementById('layerBackground').addEventListener('click', () => {
        if (!document.getElementById('layerBackground').classList.contains('disabled')) {
            switchLayer('background');
        }
    });
    document.getElementById('btnDeleteBackground').addEventListener('click', (e) => {
        e.stopPropagation(); // Ne kattintson a rétegre is
        inpaintedBackgroundBase64 = null;
        document.getElementById('layerBackground').classList.add('disabled');
        e.target.style.display = 'none';
        if (activeLayerId === 'background') switchLayer('original');
    });

    // Bal oldali eszközök bekötése
    btnDrawLasso.addEventListener('click', () => {
        if (activeLayerId !== 'original') switchLayer('original');
        toggleLasso();
    });
    btnBrushAdd.addEventListener('click', () => setBrush('add'));
    btnBrushSub.addEventListener('click', () => setBrush('sub'));
    btnApplyBrush.addEventListener('click', saveBrushMask);
    btnRefineMask.addEventListener('click', refineActiveMask);
    btnInpaintBackground.addEventListener('click', runInpainting);

    layerList.addEventListener('click', (e) => {
        const saveButton = e.target.closest('.save-btn');
        if (!saveButton) return;

        e.stopPropagation();
        const layerItem = saveButton.closest('.layer-item');
        const layerId = layerItem.dataset.id;
        let url = null;

        if (layerId === 'original' && originalImage) url = originalImage.src;
        else if (layerId === 'background' && inpaintedBackgroundBase64) url = inpaintedBackgroundBase64;
        else if (objects[layerId]) url = objects[layerId].objectBase64;

        if (url) {
            const link = document.createElement('a');
            link.download = 'layer.png';
            link.href = url;
            link.click();
        }
    }, true);

    // Ecsetméret csúszka
    brushSizeInput.addEventListener('input', (e) => {
        document.getElementById('brushSizeVal').innerText = e.target.value;
        if (canvas.freeDrawingBrush) {
            canvas.freeDrawingBrush.width = parseInt(e.target.value, 10) / canvas.getZoom();
        }
    });

    // Stable Diffusion paraméterek
    document.getElementById('sdSteps').addEventListener('input', (e) => {
        document.getElementById('sdStepsVal').innerText = e.target.value;
    });
    document.getElementById('dilationSize').addEventListener('input', (e) => {
        document.getElementById('dilationSizeVal').innerText = e.target.value;
    });
    document.getElementById('sdGuidance').addEventListener('input', (e) => {
        document.getElementById('sdGuidanceVal').innerText = e.target.value;
    });
}

function resizeCanvas() {
    canvas.setWidth(canvasContainer.clientWidth);
    canvas.setHeight(canvasContainer.clientHeight);
    canvas.renderAll();
}

// ---- KÖZPONTI ESZKÖZ KIKAPCSOLÓ ----
function deactivateAllTools() {
    isLassoMode = false;
    btnDrawLasso.classList.remove('btn-success');
    btnDrawLasso.innerText = "✏️ Select new object";
    if (lassoPolyline) { canvas.remove(lassoPolyline); lassoPolyline = null; }

    isPanningMode = false;
    document.getElementById('btnToolPan').classList.remove('active');

    isBrushMode = false;
    canvas.isDrawingMode = false;
    btnBrushAdd.classList.remove('active');
    btnBrushSub.classList.remove('active');

    canvas.defaultCursor = 'default';
}

// ---- NÉZET KEZELÉS ----
function zoomCanvas(factor) {
    let zoom = canvas.getZoom() * factor;
    canvas.zoomToPoint({ x: canvas.width / 2, y: canvas.height / 2 }, zoom);
    if (canvas.freeDrawingBrush) canvas.freeDrawingBrush.width = parseInt(brushSizeInput.value, 10) / zoom;
}

function onMouseWheel(opt) {
    let zoom = canvas.getZoom() * (0.999 ** opt.e.deltaY);
    if (zoom > 20) zoom = 20;
    if (zoom < 0.05) zoom = 0.05;
    canvas.zoomToPoint({ x: opt.e.offsetX, y: opt.e.offsetY }, zoom);
    if (canvas.freeDrawingBrush) canvas.freeDrawingBrush.width = parseInt(brushSizeInput.value, 10) / zoom;
    opt.e.preventDefault();
    opt.e.stopPropagation();
}

function fitImageToScreen() {
    if (!originalWidth) return;
    const zoom = Math.min(canvas.width / originalWidth, canvas.height / originalHeight) * 0.95;
    const panX = (canvas.width - originalWidth * zoom) / 2;
    const panY = (canvas.height - originalHeight * zoom) / 2;
    canvas.setViewportTransform([zoom, 0, 0, zoom, panX, panY]);
    if (canvas.freeDrawingBrush) canvas.freeDrawingBrush.width = parseInt(brushSizeInput.value, 10) / zoom;
}

function togglePanMode() {
    const wasPanning = isPanningMode;
    deactivateAllTools();
    if (!wasPanning) {
        isPanningMode = true;
        document.getElementById('btnToolPan').classList.add('active');
        canvas.defaultCursor = 'grab';
    }
}

// ---- KÉP FELTÖLTÉS ----
imageInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    statusMessage.innerText = "⏳ Uploading image...";
    const formData = new FormData(); formData.append('image', file);

    try {
        const res = await fetch('/api/upload/', { method: 'POST', body: formData });
        const data = await res.json();
        if (res.ok) {
            currentSessionId = data.session_id;
            originalWidth = data.width;
            originalHeight = data.height;
            const reader = new FileReader();
            reader.onload = (evt) => {
                const img = new Image();
                img.onload = () => {
                    originalImage = img;
                    objects = {};
                    dynamicObjectLayers.innerHTML = '';
                    inpaintedBackgroundBase64 = null;
                    document.getElementById('layerBackground').classList.add('disabled');
                    document.getElementById('btnDeleteBackground').style.display = 'none';

                    document.getElementById('toolsSection').style.display = 'flex';
                    document.getElementById('actionSection').style.display = 'flex';
                    statusMessage.innerText = "✅ Image loaded! The original layer is active.";

                    switchLayer('original'); // Egyből az eredetit töltjük be
                    fitImageToScreen();
                };
                img.src = evt.target.result;
            };
            reader.readAsDataURL(file);
        }
    } catch (err) { statusMessage.innerText = "❌ Upload failed."; }
});

// Alapkép renderelése
function renderBaseImage(imgElement) {
    const fImg = new fabric.Image(imgElement, {
        left: 0, top: 0, selectable: false, evented: false, name: 'baseImg'
    });
    canvas.add(fImg);
    canvas.sendToBack(fImg);
}

// ---- RÉTEG VÁLTÁS ----
function switchLayer(layerId) {
    activeLayerId = layerId;
    deactivateAllTools();

    // Stílusok frissítése a jobb oldali menüben
    document.querySelectorAll('.layer-item').forEach(el => el.classList.remove('active'));
    document.querySelector(`.layer-item[data-id="${layerId}"]`)?.classList.add('active');

    // Teljes vászon törlése
    canvas.clear();

    // Aktív kép betöltése
    if (layerId === 'original') {
        renderBaseImage(originalImage);
    }
    else if (layerId === 'background' && inpaintedBackgroundBase64) {
        const img = new Image();
        img.onload = () => renderBaseImage(img);
        img.src = inpaintedBackgroundBase64;
    }
    else if (objects[layerId]) {
        // Objektum esetén: Eredeti kép alulra, vörös maszk felülre
        renderBaseImage(originalImage);
        fabric.Image.fromURL(objects[layerId].maskOverlayBase64, (img) => {
            img.set({ selectable: false, evented: false, name: 'maskOverlay' });
            canvas.add(img);
        });
    }

    const propType = document.getElementById('propType');
    const propSize = document.getElementById('propSize');
    const propCoverage = document.getElementById('propCoverage');
    const propPromptRow = document.getElementById('propPromptRow');
    const propPrompt = document.getElementById('propPrompt');
    const imageSize = `${originalWidth} x ${originalHeight} px`;

    if (layerId === 'original') {
        propType.innerText = 'Original Image';
        propSize.innerText = imageSize;
        propCoverage.innerText = '100%';
        propPromptRow.style.display = 'none';
    } else if (layerId === 'background') {
        propType.innerText = 'Generated Background';
        propSize.innerText = imageSize;
        propCoverage.innerText = '100%';
        propPromptRow.style.display = 'flex';
        propPrompt.innerText = lastUsedPrompt;
    } else if (objects[layerId]) {
        propType.innerText = 'AI Selection Mask';
        propSize.innerText = imageSize;
        propCoverage.innerText = 'Partial (Mask)';
        propPromptRow.style.display = 'none';
    }
}

// ---- LASSZÓ KIJELÖLÉS ----
function toggleLasso() {
    if (isLassoMode) {
        sendLassoToBackend(); // Ha be volt kapcsolva, elküldjük
    } else {
        deactivateAllTools();
        isLassoMode = true;
        btnDrawLasso.innerText = "✅ Finish selection";
        btnDrawLasso.classList.add('btn-success');
        canvas.defaultCursor = 'crosshair';
        lassoPoints = [];
        statusMessage.innerText = "✏️ Outline the object, then press the Finish button when done.";
    }
}

function onMouseDown(opt) {
    isMouseDown = true;
    if (isPanningMode) {
        canvas.defaultCursor = 'grabbing';
        panLastX = opt.e.clientX;
        panLastY = opt.e.clientY;
        return;
    }
    if (isLassoMode) {
        const ptr = canvas.getPointer(opt.e);
        lassoPoints.push({ x: ptr.x, y: ptr.y });
    }
}

function onMouseMove(opt) {
    if (!isMouseDown) return;
    if (isPanningMode) {
        const vpt = canvas.viewportTransform;
        vpt[4] += opt.e.clientX - panLastX;
        vpt[5] += opt.e.clientY - panLastY;
        canvas.requestRenderAll();
        panLastX = opt.e.clientX;
        panLastY = opt.e.clientY;
        return;
    }
    if (isLassoMode) {
        const ptr = canvas.getPointer(opt.e);
        lassoPoints.push({ x: ptr.x, y: ptr.y });

        if (lassoPolyline) canvas.remove(lassoPolyline);
        lassoPolyline = new fabric.Polyline(lassoPoints, {
            stroke: '#38bdf8', strokeWidth: 4 / canvas.getZoom(),
            fill: 'rgba(56, 189, 248, 0.2)', selectable: false, evented: false
        });
        canvas.add(lassoPolyline);
        canvas.renderAll();
    }
}

function onMouseUp() {
    isMouseDown = false;
    if (isPanningMode) canvas.defaultCursor = 'grab';
}

async function sendLassoToBackend() {
    const pts = lassoPoints;
    deactivateAllTools();

    if (pts.length < 3) return;

    objectCounter++;
    const newObjId = `obj_${objectCounter}`;
    const realPolygon = pts.map(p => [Math.round(p.x), Math.round(p.y)]);

    statusMessage.innerText = "⚡ SAM analysis in progress...";
    try {
        const res = await fetch('/api/segment-lasso/', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, obj_id: newObjId, polygon: realPolygon, refine: true })
        });
        const data = await res.json();
        if (res.ok) {
            objects[newObjId] = { name: `Object ${objectCounter}`, maskOverlayBase64: data.mask_overlay_base64, objectBase64: data.object_base64 };
            addDynamicLayerItem(newObjId, `Object ${objectCounter}`);
            switchLayer(newObjId);
            statusMessage.innerText = `✨ Selection complete! Refine it with the brush.`;
        }
    } catch (err) { }
}

function addDynamicLayerItem(objId, title) {
    const item = document.createElement('div');
    item.className = 'layer-item';
    item.dataset.id = objId;
    item.innerHTML = `
        <div class="layer-preview-box">✂️</div>
        <div class="layer-info"><span class="layer-title">${title}</span></div>
        <div class="layer-actions">
            <button class="save-btn" title="Save layer">💾</button>
            <button class="delete-btn" title="Delete layer">🗑️</button>
        </div>
    `;
    item.addEventListener('click', (e) => {
        if (e.target.classList.contains('delete-btn')) {
            delete objects[objId];
            item.remove();
            if (activeLayerId === objId) switchLayer('original');
        } else {
            switchLayer(objId);
        }
    });
    dynamicObjectLayers.appendChild(item);
}

// ---- KÉZI ECSET MÓD ----
function setBrush(mode) {
    if (activeLayerId === 'original' || activeLayerId === 'background') {
        statusMessage.innerText = "⚠️ You can only use the brush on an existing object layer!";
        return;
    }
    deactivateAllTools();
    isBrushMode = true;
    canvas.isDrawingMode = true;
    canvas.freeDrawingBrush = new fabric.PencilBrush(canvas);
    canvas.freeDrawingBrush.width = parseInt(brushSizeInput.value, 10) / canvas.getZoom();

    // Kék hozzáad, Fekete radíroz
    canvas.freeDrawingBrush.color = mode === 'add' ? 'rgba(0, 0, 255, 1)' : 'rgba(0, 0, 0, 1)';

    if (mode === 'add') btnBrushAdd.classList.add('active');
    else btnBrushSub.classList.add('active');

    statusMessage.innerText = mode === 'add' ? "➕ Expand mask (draw in blue)" : "➖ Erase mask (draw in black)";
}

async function saveBrushMask() {
    if (activeLayerId === 'original' || activeLayerId === 'background' || !isBrushMode) return;
    deactivateAllTools();
    statusMessage.innerText = "💾 Saving changes to the server...";

    // Eltüntetjük a háttérképet mentés előtt
    const bg = canvas.getObjects().find(o => o.name === 'baseImg');
    if (bg) bg.opacity = 0;

    // Vászont 1:1 méretbe rakjuk a tökéletes exportáláshoz
    const oldW = canvas.width;
    const oldH = canvas.height;
    const oldVpt = canvas.viewportTransform.slice();

    canvas.setViewportTransform([1, 0, 0, 1, 0, 0]);
    canvas.setWidth(originalWidth);
    canvas.setHeight(originalHeight);
    canvas.renderAll();

    const maskDataUrl = canvas.toDataURL({ format: 'png', left: 0, top: 0, width: originalWidth, height: originalHeight });

    // Visszaállítjuk a képernyőt
    if (bg) bg.opacity = 1;
    canvas.setWidth(oldW);
    canvas.setHeight(oldH);
    canvas.setViewportTransform(oldVpt);
    canvas.renderAll();

    try {
        const res = await fetch('/api/update-mask/', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, obj_id: activeLayerId, mask_base64: maskDataUrl })
        });
        const data = await res.json();
        if (res.ok) {
            objects[activeLayerId].maskOverlayBase64 = data.mask_overlay_base64;
            objects[activeLayerId].objectBase64 = data.object_base64;
            switchLayer(activeLayerId);
            statusMessage.innerText = "✅ Mask updated successfully!";
        }
    } catch (err) { }
}

async function refineActiveMask() {
    if (activeLayerId === 'original' || activeLayerId === 'background') return;
    deactivateAllTools();
    statusMessage.innerText = "✨ Refining mask on the server...";
    try {
        const res = await fetch('/api/refine-mask/', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, obj_id: activeLayerId })
        });
        const data = await res.json();
        if (res.ok) {
            objects[activeLayerId].maskOverlayBase64 = data.mask_overlay_base64;
            switchLayer(activeLayerId);
            statusMessage.innerText = "✅ Mask refined.";
        }
    } catch (err) { }
}

// ---- HÁTTÉR KITÖLTÉS (Stable Diffusion) ----
async function runInpainting() {
    if (!currentSessionId || Object.keys(objects).length === 0) {
        statusMessage.innerText = "⚠️ No object selected."; return;
    }
    deactivateAllTools();
    statusMessage.innerText = "🎨 Running inpainting on the server (this may take a few seconds)...";

    const dilationValue = parseInt(document.getElementById('dilationSize').value, 10);
    const prompt = document.getElementById('sdPrompt').value;
    const negativePrompt = document.getElementById('sdNegativePrompt').value;
    const steps = parseInt(document.getElementById('sdSteps').value, 10);
    const guidance = parseFloat(document.getElementById('sdGuidance').value);

    try {
        const res = await fetch('/api/inpaint/', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                dilation: dilationValue,
                prompt: prompt,
                negative_prompt: negativePrompt,
                steps: steps,
                guidance: guidance
            })
        });
        const data = await res.json();
        if (res.ok) {
            lastUsedPrompt = document.getElementById('sdPrompt').value;
            inpaintedBackgroundBase64 = data.inpainted_base64;
            document.getElementById('layerBackground').classList.remove('disabled');
            document.getElementById('btnDeleteBackground').style.display = 'inline-block';
            switchLayer('background');
            statusMessage.innerText = "🎉 Background filled successfully!";
        }
    } catch (err) { }
}

// App indítása a betöltés végén
window.onload = initApp;