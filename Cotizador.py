import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
import os
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

class GeneradorCotizacionesMadera:
    def __init__(self):
        self.productos = None
        self.listas_precio = {
            'LP1': 'Lista de Precios 1',
            'LP2': 'Lista de Precios 2', 
            'LP3': 'Lista de Precios 3'
        }
        
    def cargar_excel_automatico(self):
        """Cargar productos desde archivo Excel automáticamente"""
        file_path = "preciosItens2 septo 2025.xls"
        
        try:
            if not os.path.exists(file_path):
                return {
                    'exito': False,
                    'error': f"No se encontró el archivo '{file_path}'",
                    'mensaje': f'Archivo {file_path} no encontrado en el directorio'
                }
            
            # Leer el archivo Excel
            df = pd.read_excel(file_path, engine='xlrd')
            
            # Limpiar nombres de columnas
            df.columns = df.columns.str.strip()
            
            # Filtrar filas con referencia y descripción válidas
            df = df.dropna(subset=['Referencia', 'Desc. item'])
            df = df[df['Referencia'].str.strip() != '']
            df = df[df['Desc. item'].str.strip() != '']
            
            # Limpiar referencias (quitar espacios en blanco al final)
            df['Referencia'] = df['Referencia'].str.strip()
            
            # Limpiar precios (convertir a numérico)
            columnas_precio = ['LP1', 'LP2', 'LP3']
            
            for col in columnas_precio:
                if col in df.columns:
                    df[col] = df[col].apply(self.limpiar_precio)
            
            # Llenar valores nulos de LP2 con LP1 si existe
            if 'LP2' in df.columns and 'LP1' in df.columns:
                df['LP2'] = df['LP2'].fillna(df['LP1'])
            
            self.productos = df
            
            return {
                'exito': True,
                'total_productos': len(df),
                'mensaje': f'Excel cargado exitosamente con {len(df)} productos',
                'columnas': list(df.columns)
            }
        except Exception as e:
            return {
                'exito': False,
                'error': str(e),
                'mensaje': 'Error al cargar el archivo Excel'
            }
    
    def limpiar_precio(self, precio):
        """Limpiar y convertir precio a número"""
        if pd.isna(precio):
            return 0
        
        # Si ya es numérico, devolverlo
        if isinstance(precio, (int, float)):
            return float(precio)
        
        # Convertir a string y limpiar
        precio_str = str(precio)
        # Remover caracteres no numéricos excepto punto y coma
        precio_limpio = re.sub(r'[^\d.,]', '', precio_str)
        # Remover comas (separadores de miles)
        precio_limpio = precio_limpio.replace(',', '')
        
        try:
            return float(precio_limpio)
        except:
            return 0
    
    def formatear_precio(self, precio):
        """Formatear precio como moneda colombiana"""
        if pd.isna(precio) or precio == 0:
            return "$ 0"
        return f"$ {precio:,.0f}".replace(',', '.')
    
    def buscar_productos(self, termino_busqueda, lista_precio='LP1', limite=10, categoria_filtro=None):
        """Buscar productos por descripción"""
        if self.productos is None or self.productos.empty:
            return {
                'exito': False,
                'mensaje': 'No hay productos cargados'
            }
        
        # Filtrar productos que contengan el término de búsqueda en descripción o referencia
        mask_desc = self.productos['Desc. item'].str.contains(
            termino_busqueda, 
            case=False, 
            na=False
        )
        
        mask_ref = self.productos['Referencia'].str.contains(
            termino_busqueda, 
            case=False, 
            na=False
        )
        
        mask_desc_corta = self.productos['Desc. corta item'].str.contains(
            termino_busqueda, 
            case=False, 
            na=False
        )
        
        # Combinar máscaras con OR
        mask = mask_desc | mask_ref | mask_desc_corta
        
        # Filtro adicional por categoría (basado en prefijo de referencia)
        if categoria_filtro:
            mask_categoria = self.productos['Referencia'].str.startswith(
                categoria_filtro.upper(), 
                na=False
            )
            mask = mask & mask_categoria
        
        resultados = self.productos[mask].head(limite)
        
        if resultados.empty:
            return {
                'exito': False,
                'mensaje': f'No se encontraron productos para: {termino_busqueda}'
            }
        
        # Formatear resultados
        productos_formateados = []
        for _, producto in resultados.iterrows():
            producto_formateado = self.formatear_producto(producto, lista_precio)
            productos_formateados.append(producto_formateado)
        
        return {
            'exito': True,
            'resultados': productos_formateados,
            'total': len(productos_formateados)
        }
    
    def formatear_producto(self, producto, lista_precio='LP1'):
        """Formatear un producto con toda la información"""
        precio = producto.get(lista_precio, 0)
        
        return {
            'referencia': producto.get('Referencia', ''),
            'descripcion': producto.get('Desc. item', ''),
            'descripcion_corta': producto.get('Desc. corta item', ''),
            'notas': producto.get('Notas ítem', ''),
            'lista_precio': lista_precio,
            'precio': self.formatear_precio(precio),
            'precio_numerico': precio,
            'precios': {
                'LP1': producto.get('LP1', 0),
                'LP2': producto.get('LP2', 0),
                'LP3': producto.get('LP3', 0)
            }
        }
    
    def obtener_categorias(self):
        """Obtener categorías basadas en prefijos de referencia"""
        if self.productos is None or self.productos.empty:
            return []
        
        # Extraer primeros 6 caracteres de las referencias para categorías
        prefijos = self.productos['Referencia'].str[:6].unique()
        prefijos = [p for p in prefijos if p and str(p).strip()]
        
        return sorted(prefijos)
    
    def generar_cotizacion(self, productos_seleccionados, datos_cliente, opciones=None):
        """Generar cotización completa"""
        if opciones is None:
            opciones = {}
            
        lista_precio = opciones.get('lista_precio', 'LP1')
        descuento_porcentaje = opciones.get('descuento', 0)
        validez_dias = opciones.get('validez_dias', 30)
        
        subtotal = 0
        items_cotizacion = []
        
        for item in productos_seleccionados:
            cantidad = item.get('cantidad', 1)
            precio_unitario = item['precio_numerico']
            total_item = cantidad * precio_unitario
            subtotal += total_item
            
            items_cotizacion.append({
                'referencia': item['referencia'],
                'descripcion': item['descripcion'],
                'descripcion_corta': item['descripcion_corta'],
                'notas': item['notas'],
                'cantidad': cantidad,
                'precio_unitario': self.formatear_precio(precio_unitario),
                'total': self.formatear_precio(total_item),
                'precio_unitario_numerico': precio_unitario,
                'total_numerico': total_item
            })
        
        # Calcular totales
        valor_descuento = subtotal * (descuento_porcentaje / 100)
        total = subtotal - valor_descuento
        
        fecha_actual = datetime.now()
        fecha_vencimiento = fecha_actual + timedelta(days=validez_dias)
        
        return {
            'numero_cotizacion': self.generar_numero_cotizacion(),
            'fecha': fecha_actual.strftime('%d/%m/%Y'),
            'fecha_vencimiento': fecha_vencimiento.strftime('%d/%m/%Y'),
            'cliente': datos_cliente,
            'lista_precio': self.listas_precio.get(lista_precio, lista_precio),
            'items': items_cotizacion,
            'resumen': {
                'subtotal': self.formatear_precio(subtotal),
                'descuento': f'{descuento_porcentaje}% - {self.formatear_precio(valor_descuento)}' if descuento_porcentaje > 0 else None,
                'total': self.formatear_precio(total),
                'subtotal_numerico': subtotal,
                'descuento_numerico': valor_descuento,
                'total_numerico': total
            },
            'condiciones': self.obtener_condiciones_generales()
        }
    
    def generar_numero_cotizacion(self):
        """Generar número único de cotización"""
        fecha = datetime.now()
        timestamp = str(int(fecha.timestamp()))[-6:]
        return f"COT-{fecha.strftime('%Y%m')}-{timestamp}"
    
    def generar_pdf_cotizacion(self, cotizacion, datos_empresa=None):
        """Generar PDF de la cotización con formato profesional"""
        buffer = BytesIO()
        
        # Configuración de la página con márgenes equilibrados
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=15*mm,
            leftMargin=15*mm,
            topMargin=15*mm,
            bottomMargin=15*mm
        )
        
        # Colores corporativos
        color_principal = colors.Color(27/255, 94/255, 32/255)  # Verde oscuro
        color_secundario = colors.Color(46/255, 125/255, 50/255)  # Verde medio
        color_acento = colors.Color(255/255, 193/255, 7/255)  # Amarillo
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=color_principal,
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        header_style = ParagraphStyle(
            'HeaderStyle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.black,
            alignment=TA_LEFT,
            fontName='Helvetica'
        )
        
        # Datos de empresa por defecto
        if datos_empresa is None:
            datos_empresa = {
                'nombre': 'Empresa',
                'nit': '900.XXX.XXX-X',
                'direccion': 'Dirección',
                'telefono': 'XXX-XXXX',
                'ciudad': 'Ciudad',
                'email': 'ventas@empresa.com'
            }
        
        # Contenido del PDF
        story = []
        
        # HEADER DE LA EMPRESA
        header_data = [
            [
                Paragraph(f"""
                <b>{datos_empresa['nombre']}</b><br/>
                NIT: {datos_empresa['nit']}<br/>
                {datos_empresa['direccion']}<br/>
                Tel: {datos_empresa['telefono']}<br/>
                {datos_empresa['ciudad']}<br/>
                {datos_empresa['email']}
                """, header_style),
                Paragraph(f"""
                <b>COTIZACIÓN</b><br/>
                No. {cotizacion['numero_cotizacion']}<br/>
                Fecha: {cotizacion['fecha']}
                """, ParagraphStyle(
                    'HeaderRight',
                    parent=styles['Normal'],
                    fontSize=12,
                    textColor=color_principal,
                    alignment=TA_RIGHT,
                    fontName='Helvetica-Bold'
                ))
            ]
        ]
        
        header_table = Table(header_data, colWidths=[4*inch, 2.5*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOX', (0, 0), (-1, -1), 1, color_principal),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        story.append(header_table)
        story.append(Spacer(1, 20))
        
        # INFORMACIÓN DEL CLIENTE
        cliente_data = [
            [
                Paragraph(f"""
                <b>Cliente:</b> {cotizacion['cliente']['nombre']}<br/>
                <b>NIT/Cédula:</b> {cotizacion['cliente'].get('nit_cedula', 'N/A')}<br/>
                <b>Empresa:</b> {cotizacion['cliente'].get('empresa', 'N/A')}<br/>
                <b>Teléfono:</b> {cotizacion['cliente'].get('telefono', 'N/A')}<br/>
                <b>Email:</b> {cotizacion['cliente'].get('email', 'N/A')}
                """, header_style),
                Paragraph(f"""
                <b>Lista de Precios:</b> {cotizacion['lista_precio']}<br/>
                <b>Vencimiento:</b> {cotizacion['fecha_vencimiento']}
                """, header_style)
            ]
        ]
        
        cliente_table = Table(cliente_data, colWidths=[4*inch, 2.5*inch])
        cliente_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, color_principal),
            ('INNERGRID', (0, 0), (-1, -1), 1, color_secundario),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        story.append(cliente_table)
        story.append(Spacer(1, 20))
        
        # TABLA DE PRODUCTOS
        productos_headers = [
            'Referencia', 'Descripción', 'Cantidad', 'Precio Unitario', 'Total'
        ]
        
        # Datos de productos
        productos_data = [productos_headers]
        
        for item in cotizacion['items']:
            productos_data.append([
                item['referencia'],
                item['descripcion'][:40] + "..." if len(item['descripcion']) > 40 else item['descripcion'],
                str(item['cantidad']),
                item['precio_unitario'],
                item['total']
            ])
        
        # Crear tabla de productos
        productos_table = Table(
            productos_data, 
            colWidths=[1.5*inch, 2.5*inch, 0.8*inch, 1.1*inch, 1.1*inch]
        )
        
        productos_table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), color_principal),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            
            # Datos
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Referencia centrada
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),     # Descripción izquierda
            ('ALIGN', (2, 1), (2, -1), 'CENTER'),   # Cantidad centrada
            ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),   # Precios a la derecha
            
            # Bordes
            ('BOX', (0, 0), (-1, -1), 1, color_principal),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, color_secundario),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        story.append(productos_table)
        story.append(Spacer(1, 20))
        
        # TOTALES
        totales_data = [
            ['', 'Subtotal:', cotizacion['resumen']['subtotal']],
        ]
        
        if cotizacion['resumen']['descuento']:
            totales_data.append(['', 'Descuento:', cotizacion['resumen']['descuento']])
        
        totales_data.append(['', 'TOTAL:', cotizacion['resumen']['total']])
        
        totales_table = Table(totales_data, colWidths=[3.5*inch, 1.5*inch, 1.5*inch])
        totales_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (1, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (1, 0), (-1, -1), 10),
            ('BOX', (1, 0), (-1, -1), 1, color_principal),
            ('INNERGRID', (1, 0), (-1, -1), 0.5, color_secundario),
            ('BACKGROUND', (1, -1), (-1, -1), colors.Color(241/255, 248/255, 233/255)),
            ('LEFTPADDING', (1, 0), (-1, -1), 8),
            ('RIGHTPADDING', (1, 0), (-1, -1), 8),
            ('TOPPADDING', (1, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (1, 0), (-1, -1), 8),
        ]))
        
        story.append(totales_table)
        story.append(Spacer(1, 30))
        
        # CONDICIONES GENERALES
        if cotizacion.get('condiciones'):
            story.append(Paragraph("<b>Condiciones Generales:</b>", 
                                 ParagraphStyle('ConditionsTitle', parent=styles['Normal'], 
                                              fontSize=10, fontName='Helvetica-Bold',
                                              textColor=color_principal)))
            story.append(Spacer(1, 8))
            
            for condicion in cotizacion['condiciones']:
                story.append(Paragraph(f"• {condicion}", 
                                     ParagraphStyle('Condition', parent=styles['Normal'], 
                                                  fontSize=9, leftIndent=10)))
        
        # Generar PDF
        doc.build(story)
        buffer.seek(0)
        return buffer
    
    def obtener_condiciones_generales(self):
        """Condiciones generales de la cotización"""
        return [
            'Los precios están sujetos a cambios sin previo aviso',
            'Tiempos de entrega sujetos a disponibilidad',
            'Se requiere anticipo para procesar el pedido',
            'Garantía según especificaciones del proveedor'
        ]
    
    def obtener_estadisticas(self):
        """Obtener estadísticas del catálogo"""
        if self.productos is None or self.productos.empty:
            return None
        
        stats = {
            'total_productos': len(self.productos),
            'categorias': self.obtener_categorias()
        }
        
        # Estadísticas de precios por lista
        for lista in ['LP1', 'LP2', 'LP3']:
            if lista in self.productos.columns:
                precios = self.productos[lista].dropna()
                if not precios.empty:
                    stats[f'precios_{lista}'] = {
                        'min': precios.min(),
                        'max': precios.max(),
                        'promedio': precios.mean(),
                        'productos_con_precio': len(precios)
                    }
        
        return stats

def main():
    # Configuración de la página
    st.set_page_config(
        page_title="Cotizador - Precios Items",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # CSS personalizado
    st.markdown("""
<style>
    .stApp {
        background-color: #FAFAFA;
    }
    
    section[data-testid="stSidebar"] {
        display: none;
    }
    
    .main-title {
        font-size: 2.5rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 2rem;
        background: linear-gradient(135deg, #1B5E20, #2E7D32);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .stButton > button {
        background-color: #1B5E20;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #2E7D32;
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(27, 94, 32, 0.3);
    }
    
    .stTextInput>div>div>input {
        background-color: #FFFFFF;
        color: #2C3E50;
        border: 1px solid #C8E6C9;
        border-radius: 8px;
    }
    
    .stSelectbox>div>div>div {
        background-color: #FFFFFF;
        color: #2C3E50;
        border: 1px solid #C8E6C9;
        border-radius: 8px;
    }
    
    .metric-container {
        background-color: #F1F8E9;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #C8E6C9;
        text-align: center;
    }
    
    .product-card {
        background-color: #FFFFFF;
        border: 1px solid #C8E6C9;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(27, 94, 32, 0.1);
        transition: all 0.3s ease;
    }
    
    .product-card:hover {
        box-shadow: 0 4px 8px rgba(27, 94, 32, 0.2);
        transform: translateY(-2px);
    }
</style>
""", unsafe_allow_html=True)
    
    # Título principal
    st.markdown('<h1 class="main-title">💰 Cotizador de Precios</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #2E7D32; font-size: 1.2rem; margin-bottom: 2rem;">Sistema de Cotizaciones</p>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Inicializar el generador
    if 'generador' not in st.session_state:
        st.session_state.generador = GeneradorCotizacionesMadera()
    
    # Cargar archivo automáticamente
    if 'catalogo_cargado' not in st.session_state:
        st.session_state.catalogo_cargado = False
    
    if not st.session_state.catalogo_cargado:
        with st.spinner('🔄 Cargando catálogo de productos...'):
            resultado = st.session_state.generador.cargar_excel_automatico()
            
            if resultado['exito']:
                st.session_state.catalogo_cargado = True
                st.success(f"✅ {resultado['mensaje']}")
            else:
                st.error(f"❌ {resultado['mensaje']}")
                st.warning("💡 Asegúrate de que el archivo 'preciosItens2 septo 2025.xls' esté en el directorio de la aplicación.")
                st.session_state.catalogo_cargado = False
    
    # Verificar si el catálogo está cargado
    if not st.session_state.get('catalogo_cargado', False):
        st.stop()
    
    # Obtener estadísticas del catálogo
    stats = st.session_state.generador.obtener_estadisticas()
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f'<div class="metric-container"><h3>{stats["total_productos"]}</h3><p>Productos Total</p></div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown(f'<div class="metric-container"><h3>{len(stats["categorias"])}</h3><p>Categorías</p></div>', unsafe_allow_html=True)
        
        with col3:
            if 'precios_LP1' in stats:
                precio_min = st.session_state.generador.formatear_precio(stats['precios_LP1']['min'])
                st.markdown(f'<div class="metric-container"><h3>{precio_min}</h3><p>Precio Mínimo</p></div>', unsafe_allow_html=True)
        
        with col4:
            if 'precios_LP1' in stats:
                precio_max = st.session_state.generador.formatear_precio(stats['precios_LP1']['max'])
                st.markdown(f'<div class="metric-container"><h3>{precio_max}</h3><p>Precio Máximo</p></div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Layout principal con dos columnas
    col_main, col_cotizacion = st.columns([2, 1])
    
    with col_main:
        # Configuración principal
        st.markdown("### ⚙️ Configuración de Búsqueda")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            lista_precio = st.selectbox(
                "💰 Lista de Precios:",
                options=['LP1', 'LP2', 'LP3'],
                format_func=lambda x: f"Lista {x[-1]}"
            )
        
        with col2:
            categorias = st.session_state.generador.obtener_categorias()
            categoria_filtro = st.selectbox(
                "📂 Categoría (Opcional):",
                options=['Todas'] + categorias[:20],  # Limitar a 20 para no sobrecargar
                index=0
            )
        
        with col3:
            aplica_descuento = st.checkbox("💸 Aplica Descuento", value=False)
        
        st.markdown("---")
        
        # Área principal - Búsqueda
        st.markdown("### 🔍 Buscar Productos")
        termino_busqueda = st.text_input(
            "Describe el producto que buscas:",
            placeholder="Ej: alambre, tabla, estacón, grapa, viga..."
        )
        
        # Realizar búsqueda
        if termino_busqueda:
            with st.spinner('🔍 Buscando productos...'):
                categoria_filter = None if categoria_filtro == 'Todas' else categoria_filtro
                
                resultados = st.session_state.generador.buscar_productos(
                    termino_busqueda, 
                    lista_precio=lista_precio,
                    limite=20,
                    categoria_filtro=categoria_filter
                )
            
            if resultados['exito']:
                filtro_info = f" en {categoria_filtro}" if categoria_filtro != 'Todas' else ""
                st.markdown(f"### 📦 Productos encontrados ({resultados['total']}){filtro_info}")
                
                # Mostrar productos en tarjetas
                for i, producto in enumerate(resultados['resultados']):
                    with st.expander(f"📦 {producto['descripcion_corta']} - {producto['precio']}"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.write(f"**📋 Referencia:** {producto['referencia']}")
                            st.write(f"**📝 Descripción:** {producto['descripcion']}")
                            st.write(f"**📄 Notas:** {producto['notas'][:50]}..." if len(producto['notas']) > 50 else f"**📄 Notas:** {producto['notas']}")
                        
                        with col2:
                            st.write(f"**💰 Lista Actual:** {producto['lista_precio']}")
                            st.write(f"**💲 Precio:** {producto['precio']}")
                            # Comparación de precios
                            st.write("**💲 Comparación de listas:**")
                            st.write(f"LP1: {st.session_state.generador.formatear_precio(producto['precios']['LP1'])}")
                            st.write(f"LP2: {st.session_state.generador.formatear_precio(producto['precios']['LP2'])}")
                            st.write(f"LP3: {st.session_state.generador.formatear_precio(producto['precios']['LP3'])}")
                        
                        with col3:
                            # Control de cantidad y botón agregar
                            cantidad = st.number_input(
                                f"Cantidad:",
                                min_value=1,
                                value=1,
                                key=f"cantidad_{i}"
                            )
                            
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button(f"🛒 Agregar a Cotización", key=f"agregar_{i}"):
                                if 'productos_cotizacion' not in st.session_state:
                                    st.session_state.productos_cotizacion = []
                                
                                producto_con_cantidad = producto.copy()
                                producto_con_cantidad['cantidad'] = cantidad
                                st.session_state.productos_cotizacion.append(producto_con_cantidad)
                                st.success(f"✅ {producto['descripcion_corta']} agregado a la cotización")
                                st.rerun()
            else:
                st.warning(f"⚠️ {resultados['mensaje']}")
        
        # Sección de cotización - Solo mostrar si hay productos seleccionados
        if 'productos_cotizacion' in st.session_state and st.session_state.productos_cotizacion:
            st.markdown("---")
            st.markdown("### 📋 Generar Cotización Final")
            
            # Resumen rápido
            total_items = sum(producto['cantidad'] for producto in st.session_state.productos_cotizacion)
            st.info(f"📊 **{len(st.session_state.productos_cotizacion)} productos diferentes** | **{total_items} items totales**")
            
            # Formulario de cliente y opciones
            st.markdown("### 👤 Datos del Cliente")
            
            col1, col2 = st.columns(2)
            
            with col1:
                nombre_cliente = st.text_input("👤 Nombre completo:")
                nit_cedula_cliente = st.text_input("🆔 NIT o Cédula:")
                empresa_cliente = st.text_input("🏢 Empresa:")
            
            with col2:
                telefono_cliente = st.text_input("📱 Teléfono:")
                email_cliente = st.text_input("📧 Email:")
                
            # Opciones de cotización
            st.markdown("### ⚙️ Opciones de Cotización")
            
            if aplica_descuento:
                col1, col2 = st.columns(2)
                
                with col1:
                    descuento = st.number_input("💸 Descuento (%):", min_value=0, max_value=50, value=0)
                
                with col2:
                    validez_dias = st.number_input("📅 Validez (días):", min_value=1, value=30)
            else:
                descuento = 0
                col1, col2, col3 = st.columns([1, 1, 1])
                
                with col1:
                    st.info("ℹ️ Sin descuento aplicado")
                
                with col2:
                    validez_dias = st.number_input("📅 Validez (días):", min_value=1, value=30)
            
            # Generar cotización
            st.markdown("---")
            if st.button("📄 Generar Cotización", type="primary", use_container_width=True):
                if nombre_cliente:
                    datos_cliente = {
                        'nombre': nombre_cliente,
                        'nit_cedula': nit_cedula_cliente,
                        'empresa': empresa_cliente,
                        'telefono': telefono_cliente,
                        'email': email_cliente
                    }
                    
                    opciones = {
                        'lista_precio': lista_precio,
                        'descuento': descuento,
                        'validez_dias': validez_dias
                    }
                    
                    cotizacion = st.session_state.generador.generar_cotizacion(
                        st.session_state.productos_cotizacion,
                        datos_cliente,
                        opciones
                    )
                    
                    # Mostrar cotización
                    st.success("✅ Cotización generada exitosamente!")
                    
                    # Guardar cotización en session_state
                    st.session_state.ultima_cotizacion = cotizacion
                    
                    # Generar PDF automáticamente
                    try:
                        datos_empresa_pdf = st.session_state.get('datos_empresa', {
                            'nombre': 'Empresa',
                            'nit': '900.XXX.XXX-X',
                            'direccion': 'Dirección',
                            'telefono': 'XXX-XXXX',
                            'ciudad': 'Ciudad',
                            'email': 'ventas@empresa.com'
                        })
                        
                        pdf_buffer = st.session_state.generador.generar_pdf_cotizacion(cotizacion, datos_empresa_pdf)
                        st.session_state.pdf_generado = pdf_buffer.getvalue()
                        st.session_state.nombre_archivo_pdf = f"Cotizacion_{cotizacion['numero_cotizacion']}.pdf"
                    except Exception as e:
                        st.error(f"❌ Error al generar PDF: {str(e)}")
                        st.session_state.pdf_generado = None
                    
                    # Mostrar información de la cotización
                    mostrar_cotizacion_completa(cotizacion)
                else:
                    st.error("❌ Por favor, ingresa al menos el nombre del cliente.")
    
    # Columna de cotización en progreso
    with col_cotizacion:
        st.markdown("## 📋 Cotización en Progreso")
        
        if 'productos_cotizacion' in st.session_state and st.session_state.productos_cotizacion:
            # Mostrar productos en formato de tarjetas
            for i, producto in enumerate(st.session_state.productos_cotizacion):
                with st.container(border=True):
                    st.markdown(f"**📦 {producto['descripcion_corta'].upper()}**")
                    st.markdown(f"📋 Ref: {producto['referencia']}")
                    
                    # Fila con cantidad, precio y botón eliminar
                    col_info1, col_info2 = st.columns(2)
                    
                    with col_info1:
                        st.markdown(f"📦 Cant: {producto['cantidad']}")
                    
                    with col_info2:
                        st.markdown(f"💰 {producto['precio']}")
                    
                    if st.button("🗑️ Eliminar", key=f"eliminar_lateral_{i}", use_container_width=True):
                        st.session_state.productos_cotizacion.pop(i)
                        st.rerun()
            
            # Total items al final
            total_items = sum(producto['cantidad'] for producto in st.session_state.productos_cotizacion)
            st.info(f"📊 **Total items:** {total_items}")
            
            # Botón para limpiar toda la cotización
            if st.button("🗑️ Limpiar Todo", type="secondary", use_container_width=True):
                st.session_state.productos_cotizacion = []
                if 'pdf_generado' in st.session_state:
                    del st.session_state.pdf_generado
                if 'ultima_cotizacion' in st.session_state:
                    del st.session_state.ultima_cotizacion
                st.rerun()
        else:
            st.info("No hay productos en la cotización")

def mostrar_cotizacion_completa(cotizacion):
    """Función para mostrar la cotización completa generada"""
    
    # Botones de acción
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Botón de descarga directo
        if st.session_state.get('pdf_generado') is not None:
            st.download_button(
                label="📄 Descargar PDF",
                data=st.session_state.pdf_generado,
                file_name=st.session_state.nombre_archivo_pdf,
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        else:
            st.error("❌ No se pudo generar el PDF")
    
    with col2:
        if st.button("🆕 Nueva Cotización", use_container_width=True):
            st.session_state.productos_cotizacion = []
            if 'pdf_generado' in st.session_state:
                del st.session_state.pdf_generado
            if 'ultima_cotizacion' in st.session_state:
                del st.session_state.ultima_cotizacion
            st.rerun()
    
    with col3:
        if st.button("⚙️ Config. Empresa", use_container_width=True):
            st.session_state.mostrar_config_empresa = True
    
    # Configuración de empresa
    if st.session_state.get('mostrar_config_empresa', False):
        configurar_datos_empresa()
    
    # Información de la cotización
    st.markdown(f"### 📄 Cotización {cotizacion['numero_cotizacion']}")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"**📅 Fecha:** {cotizacion['fecha']}\n\n**⏰ Vencimiento:** {cotizacion['fecha_vencimiento']}")
    
    with col2:
        st.info(f"**👤 Cliente:** {cotizacion['cliente']['nombre']}\n\n**🆔 NIT/Cédula:** {cotizacion['cliente'].get('nit_cedula', 'N/A')}")
    
    with col3:
        st.info(f"**💰 Lista:** {cotizacion['lista_precio']}")
    
    # Detalles de productos
    st.markdown("### 📦 Productos Cotizados")
    df_cotizacion = pd.DataFrame(cotizacion['items'])
    st.dataframe(df_cotizacion[['referencia', 'descripcion_corta', 'cantidad', 'precio_unitario', 'total']], 
               use_container_width=True,
               column_config={
                   "referencia": "📋 Referencia",
                   "descripcion_corta": "📦 Producto",
                   "cantidad": "📦 Cantidad",
                   "precio_unitario": "💰 Precio Unit.",
                   "total": "💵 Total"
               })
    
    # Resumen financiero
    st.markdown("### 💰 Resumen Financiero")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f'<div class="metric-container"><h3>{cotizacion["resumen"]["subtotal"]}</h3><p>Subtotal</p></div>', unsafe_allow_html=True)
    
    with col2:
        if cotizacion['resumen']['descuento']:
            st.markdown(f'<div class="metric-container"><h3>{cotizacion["resumen"]["descuento"]}</h3><p>Descuento</p></div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown(f'<div class="metric-container" style="background-color: #E8F5E8; border: 2px solid #1B5E20;"><h2 style="color: #1B5E20;">{cotizacion["resumen"]["total"]}</h2><p><strong>TOTAL</strong></p></div>', unsafe_allow_html=True)

def configurar_datos_empresa():
    """Función para configurar los datos de la empresa"""
    st.markdown("---")
    st.markdown("### 🏢 Configuración de Empresa para PDF")
    
    col1, col2 = st.columns(2)
    
    with col1:
        nombre_empresa = st.text_input("🏢 Nombre de la empresa:", 
                                     value=st.session_state.get('empresa_nombre', 'Empresa'))
        nit_empresa = st.text_input("📄 NIT:", 
                                   value=st.session_state.get('empresa_nit', '900.XXX.XXX-X'))
        direccion_empresa = st.text_input("📍 Dirección:", 
                                         value=st.session_state.get('empresa_direccion', 'Dirección'))
    
    with col2:
        telefono_empresa = st.text_input("📱 Teléfono:", 
                                       value=st.session_state.get('empresa_telefono', 'XXX-XXXX'))
        ciudad_empresa = st.text_input("🏙️ Ciudad:", 
                                     value=st.session_state.get('empresa_ciudad', 'Ciudad'))
        email_empresa = st.text_input("📧 Email:", 
                                    value=st.session_state.get('empresa_email', 'ventas@empresa.com'))
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 Guardar Configuración", use_container_width=True):
            # Guardar datos de empresa
            st.session_state.datos_empresa = {
                'nombre': nombre_empresa,
                'nit': nit_empresa,
                'direccion': direccion_empresa,
                'telefono': telefono_empresa,
                'ciudad': ciudad_empresa,
                'email': email_empresa
            }
            st.session_state.mostrar_config_empresa = False
            
            # Regenerar PDF con nuevos datos
            if 'ultima_cotizacion' in st.session_state:
                try:
                    pdf_buffer = st.session_state.generador.generar_pdf_cotizacion(
                        st.session_state.ultima_cotizacion, 
                        st.session_state.datos_empresa
                    )
                    st.session_state.pdf_generado = pdf_buffer.getvalue()
                except:
                    pass
            
            st.success("✅ Configuración guardada")
            st.rerun()
    
    with col2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.session_state.mostrar_config_empresa = False
            st.rerun()

if __name__ == "__main__":
    main()
