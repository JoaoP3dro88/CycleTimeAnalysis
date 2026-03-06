# Fase 1 — Dataset e Treino YOLO para Garras Robóticas

Guia completo para criar o modelo `.onnx` que será integrado ao app
na Fase 2. Tempo estimado: **meio dia**.

---

## Pré-requisitos locais

```powershell
# Instalar dependências dos scripts de tooling (fora do venv do backend)
pip install opencv-python numpy onnxruntime ultralytics
```

---

## Passo 1 — Extrair frames do vídeo

```powershell
cd C:\Users\klj1ct\Desktop\CycleTimeAnalysis

# Extrai ~1 frame a cada 15 (≈2 fps num vídeo de 30fps)
# Ajuste --interval conforme a velocidade do movimento da garra
python tools/extract_frames.py `
  --video  data/videos/SEU_VIDEO.mp4 `
  --output tools/frames `
  --interval 15 `
  --max 300
```

**Dica:** 150–300 frames bem variados são suficientes para um primeiro modelo.
Inclua frames com diferentes poses, iluminações e distâncias da garra.

---

## Passo 2 — Criar projeto no Roboflow e anotar

1. Acesse [roboflow.com](https://roboflow.com) → crie conta gratuita
2. **New Project** → tipo: *Object Detection*
3. Nome do projeto: `robot-gripper` (ou similar)
4. **Upload Images** → selecione toda a pasta `tools/frames/`
5. **Annotate** → desenhe bounding boxes em volta das garras em cada frame
   - Use uma classe por tipo de garra: ex. `gripper`, `gripper_open`, `gripper_closed`
   - Ou simplificado: apenas `gripper` (1 classe)
6. **Generate Dataset** → split recomendado: **70% train / 20% val / 10% test**
7. Aplique augmentações: *Flip horizontal*, *Rotation ±15°*, *Brightness ±20%*

> 💡 O Roboflow tem datasets públicos de robôs industriais.
> Antes de anotar do zero, pesquise em [universe.roboflow.com](https://universe.roboflow.com)
> por "robot gripper" ou "robotic arm" — pode economizar horas.

---

## Passo 3 — Treinar no Google Colab

Crie um novo notebook no [Google Colab](https://colab.research.google.com)
com GPU (Runtime → Change runtime type → T4 GPU) e execute:

```python
# Célula 1 — Instalar YOLOv8
!pip install ultralytics roboflow -q

# Célula 2 — Baixar dataset do Roboflow
# (substitua com o snippet gerado pelo Roboflow em Export → YOLOv8)
from roboflow import Roboflow
rf = Roboflow(api_key="SUA_API_KEY")
project = rf.workspace("SEU_WORKSPACE").project("robot-gripper")
version = project.version(1)
dataset = version.download("yolov8")

# Célula 3 — Treinar YOLOv8n (nano — ideal para browser/edge)
from ultralytics import YOLO

model = YOLO("yolov8n.pt")          # nano: rápido e leve (~6MB)
results = model.train(
    data=f"{dataset.location}/data.yaml",
    epochs=80,
    imgsz=640,
    batch=16,
    name="robot_gripper",
    patience=20,               # early stopping
)

# Célula 4 — Avaliar no conjunto de teste
metrics = model.val()
print(f"mAP50: {metrics.box.map50:.3f}")
print(f"mAP50-95: {metrics.box.map:.3f}")

# Célula 5 — Exportar para ONNX (formato para o browser)
model.export(format="onnx", imgsz=640, opset=12, simplify=True)
# Arquivo gerado: runs/detect/robot_gripper/weights/best.onnx
```

**Resultados esperados para um bom modelo:**
- mAP50 > 0.85 → pronto para integrar
- mAP50 entre 0.65–0.85 → funcional, melhora com mais dados
- mAP50 < 0.65 → adicionar mais frames/anotações

---

## Passo 4 — Baixar e validar o modelo

1. Baixe do Colab:
   - `runs/detect/robot_gripper/weights/best.onnx`
   - Crie `tools/model/classes.txt` com uma classe por linha (ex: `gripper`)
2. Salve em `tools/model/robot_gripper.onnx`
3. Valide localmente:

```powershell
python tools/validate_onnx.py `
  --model  tools/model/robot_gripper.onnx `
  --source tools/frames `
  --conf   0.35 `
  --output tools/frames_annotated `
  --show
```

Verifique visualmente se as bounding boxes estão corretas antes de integrar.

---

## Passo 5 — Preparar para a Fase 2

Coloque o modelo final aqui (pasta criada automaticamente se não existir):

```
tools/model/
  robot_gripper.onnx   ← modelo exportado
  classes.txt          ← uma classe por linha
```

O arquivo `tools/model/` está no `.gitignore` (modelos são grandes).
Quando estiver pronto, avise para começarmos a **Fase 2 — Integração no app**.

---

## Referências

- [YOLOv8 Docs](https://docs.ultralytics.com)
- [Roboflow Universe — Robot Gripper](https://universe.roboflow.com/search?q=robot+gripper)
- [ONNX Runtime Web](https://onnxruntime.ai/docs/get-started/with-javascript/web.html)
- [Google Colab com GPU](https://colab.research.google.com)
