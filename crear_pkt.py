import os
from flask import Flask, render_template
from dotenv import load_dotenv
from routes.validation_routes import validation_bp

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Registrar el Blueprint de validación
app.register_blueprint(validation_bp)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    # Configurar puerto y host por defecto, con debug activado para desarrollo
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='127.0.0.1', port=port)
