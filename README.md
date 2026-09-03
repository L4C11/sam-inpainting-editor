# AI Inpainting Workspace 🎨

A minimalist, Django-based web application for advanced AI image editing. This tool combines the power of the **Segment Anything Model (SAM)** for precise object masking with **Stable Diffusion** for seamless generative inpainting. 

## ✨ Features

* **Smart Selection (SAM):** Draw a rough lasso around an object, and the Segment Anything Model automatically snaps to the exact edges.
* **Generative Inpainting:** Replace backgrounds or remove objects using Stable Diffusion seamlessly.
* **Layer Management:** A non-destructive, layer-based workflow with visibility toggles and active layer properties.
* **Invisible Metadata:** All generation parameters (Prompt, Negative Prompt, Steps, Guidance) are automatically embedded into the exported PNG chunks.
* **Modern UI/UX:** A dark-themed, dot-grid canvas with floating toolbars and icon-driven actions.

## 🛠️ Tech Stack

* **Backend:** Django, Python, OpenCV, PIL (Pillow)
* **AI Models:** Segment Anything (Meta), Stable Diffusion (Hugging Face `diffusers`)
* **Frontend:** Vanilla JavaScript, HTML5 Canvas, Custom CSS
* **Infrastructure:** Docker & Docker Compose

## 🚀 Quick Start (Docker)

Because this project is fully containerized, installation is completely frictionless. You do not need to install Python or any dependencies manually on your host machine.

### Prerequisites
* [Docker](https://docs.docker.com/get-docker/) and Docker Compose installed.
* An NVIDIA GPU with CUDA drivers installed (highly recommended for AI inference speed).

### Installation  

1. **Clone the repository:**  
   git clone https://github.com/L4C11/sam-inpainting-editor.git  
   cd sam-inpainting-editor  
   
2. Set up environment variables:  
Create a .env file in the root directory (you can copy .env.example if available) and configure any required API keys or model paths.  

3. Build and spin up the containers:  
   docker-compose up --build  
  
4. Access the application:    
   Open your browser and navigate to:    
   http://localhost:8000  

🧠 Usage Workflow   
Upload: Click the folder icon in the left toolbar to load your base image.  

Select: Select the Lasso tool (✏️) and draw roughly around your target object. SAM will snap to the edges.  

Refine (Optional): Use the manual brush to add/subtract from the AI-generated mask.  

Generate: Adjust your Stable Diffusion parameters (Prompts, Steps, Guidance) in the left panel and hit the Inpaint button.

Export: Click the Save (💾) icon on your generated layer in the right sidebar to download the image with embedded prompt metadata.

📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
