# Cómo construir un asistente de seguridad con IA Generativa usando Amazon Bedrock y AWS

[Read in English](./README.md) | [Leia em português](./README.pt.md)

[Amazon Bedrock](https://aws.amazon.com/bedrock/) es un servicio totalmente gestionado que ofrece una selección de modelos fundacionales (FM) de alto rendimiento de las principales empresas de IA a través de una sola API, junto con un amplio conjunto de capacidades necesarias para crear aplicaciones de IA generativa, simplificando el desarrollo y manteniendo la privacidad y la seguridad. Utilizando Amazon Bedrock, es posible construir un portal de autoservicio web que permite validar si una política de [AWS Identity and Access Management (IAM)](https://aws.amazon.com/iam/) cumple con el principio de mínimo privilegio, e incluso generar nuevas políticas a partir de descripciones en lenguaje natural — buscando agilizar el proceso de aprobación de permisos dentro de una organización sin comprometer la seguridad.

Las organizaciones se encuentran en constante evolución desarrollando nuevos proyectos y aplicaciones. Parte esencial para el funcionamiento de estas aplicaciones es que cuenten con permisos y accesos para realizar distintas acciones en servicios y recursos de AWS. Estas acciones se especifican a través de [políticas IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html), las cuales se expresan en formato JSON.

Es normal que las áreas dueñas de los proyectos realicen solicitudes de permisos para el funcionamiento de sus aplicaciones y que el área de seguridad de la organización valide, apruebe o rechace estas solicitudes. El problema surge cuando las áreas de proyecto solicitan accesos que no cumplen con el principio de mínimo privilegio. Asimismo, este problema se incrementa cuando las áreas de seguridad no cuentan con los detalles del alcance de estas aplicaciones y deben limitarse a hacer cumplir las buenas prácticas. Debido a la necesidad de aprobación de permisos, la interacción entre las áreas de desarrollo y aplicaciones puede convertirse en un cuello de botella que retrase la entrega de nuevos proyectos y funcionalidades para la organización.

![security-flow](./images/security_flow.png)

Los equipos dueños de aplicaciones realizan una o varias interacciones con el área de seguridad, con el objetivo de obtener los accesos que requieren sus aplicaciones.

Que las solicitudes de permisos cumplan con el principio de mínimo privilegio desde su primera solicitud acelera el proceso de aprobación, disminuye los cuellos de botella y reduce la frustración de los usuarios.

## Portal de Autoservicio Web

La aplicación es un portal de autoservicio web con dos funcionalidades principales:

### Analizar Política

Los usuarios pueden pegar una política IAM en formato JSON y recibir un análisis detallado. Amazon Bedrock (Claude Sonnet 4.5) valida la sintaxis de la política, evalúa su cumplimiento con el principio de mínimo privilegio basándose en la especificidad de acciones, restricción de recursos, efectos y condiciones, destaca los puntos de mejora potenciales y entrega un puntaje de cumplimiento en una escala de 1 a 10. Adicionalmente, [IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html) valida la política para detectar errores de sintaxis, advertencias de seguridad y sugerencias de buenas prácticas.

Después del análisis inicial, los usuarios pueden continuar la conversación — pidiendo al asistente que corrija problemas específicos, agregue condiciones, restrinja recursos o genere una versión mejorada de la política.

### Generar Política

Los usuarios pueden describir los permisos que necesitan en lenguaje natural, y el asistente genera una política IAM siguiendo el principio de mínimo privilegio. Si la solicitud es demasiado amplia (ej., "acceso completo a EC2"), el asistente solicita detalles más específicos en lugar de generar una política insegura. Los usuarios pueden refinar la política a través de la conversación — por ejemplo, pidiendo restringir a una región específica, agregar condiciones basadas en tags o incluir permisos adicionales.

Las políticas generadas son validadas automáticamente por IAM Access Analyzer antes de ser entregadas al usuario.

![website](./images/security-assistant.gif)

## Arquitectura

El siguiente diagrama de arquitectura describe el funcionamiento del portal de autoservicio.

![architecture_diagram](./images/architecture_diagram.png)

El portal de autoservicio utiliza [Amazon CloudFront](https://aws.amazon.com/cloudfront/) (1) como punto de entrada único, sirviendo tanto el frontend React desde un bucket de [Amazon S3](https://aws.amazon.com/s3/) (2) como actuando de proxy para las llamadas API hacia [Amazon API Gateway](https://aws.amazon.com/api-gateway/) (3). CloudFront agrega un header secreto de origen a las solicitudes API, asegurando que solo las solicitudes a través de CloudFront lleguen al backend.

API Gateway invoca las funciones [AWS Lambda](https://aws.amazon.com/lambda/) (4), las cuales envían la política a [Amazon Bedrock](https://aws.amazon.com/bedrock/) (5) para análisis o generación usando Claude Sonnet 4.5, y a [IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html) (6) para validación verificada de la política. Todas las solicitudes se registran en [Amazon DynamoDB](https://aws.amazon.com/dynamodb/) (7) para fines de auditoría.

Tanto CloudFront como API Gateway están protegidos por [AWS WAFv2](https://aws.amazon.com/waf/) con grupos de reglas administradas para reputación de IP, exploits comunes e inputs maliciosos conocidos.

## Seguridad

- El API Gateway no está expuesto directamente a internet — todo el tráfico fluye a través de CloudFront, que agrega un header secreto de verificación de origen. Las funciones Lambda rechazan solicitudes sin este header.
- [AWS WAFv2](https://aws.amazon.com/waf/) protege tanto CloudFront como API Gateway con tres grupos de reglas administradas de AWS: lista de reputación de IP, conjunto de reglas comunes e inputs maliciosos conocidos.
- Todo el tráfico está cifrado en tránsito (HTTPS obligatorio, TLS 1.2 mínimo).
- Los buckets S3 tienen el acceso público completamente bloqueado; el acceso es solo a través de CloudFront Origin Access Control (OAC).
- Los roles de ejecución de Lambda siguen el principio de mínimo privilegio — limitados a ARNs específicos del modelo Bedrock y la tabla DynamoDB.
- API Gateway tiene un plan de uso con limitación de tasa (10 req/s) y cuota diaria (1.000 solicitudes).
- Todas las solicitudes se registran en DynamoDB para auditoría y en CloudWatch para observabilidad.
- El rastreo X-Ray está habilitado en Lambda y API Gateway.

## Guía de Implementación

La solución se despliega usando [AWS CDK](https://aws.amazon.com/cdk/). Los modelos de Amazon Bedrock son [accesibles automáticamente](https://aws.amazon.com/blogs/security/simplified-amazon-bedrock-model-access/) — no se requiere habilitación manual.

### Prerrequisitos

- Python 3.13+
- Node.js 18+
- AWS CDK CLI (`npm install -g aws-cdk`)
- AWS CLI configurado con las credenciales apropiadas

### Configuración inicial (una sola vez)

```bash
git clone https://github.com/aws-samples/policy-security-assistant.git
cd policy-security-assistant
npm install --prefix frontend
python -m venv cdk/.venv
source cdk/.venv/bin/activate
pip install -r cdk/requirements.txt
```

### Compilar y desplegar

```bash
npm run build --prefix frontend
cdk bootstrap --app "python cdk/app.py"  # solo necesario en el primer despliegue
cdk deploy --app "python cdk/app.py"
```

El stack de CDK creará los recursos definidos en la arquitectura. Una vez finalizado el despliegue, la URL del sitio web de CloudFront se mostrará en los outputs. Abra el enlace para acceder al asistente de seguridad.

No se necesita configuración adicional — CloudFront sirve tanto el frontend como la API, por lo que no hay URLs de API ni claves que configurar manualmente.

### Redesplegar después de cambios

- Cambios solo en Lambda: `cdk deploy --app "python cdk/app.py"`
- Cambios en el frontend: `npm run build --prefix frontend` y luego `cdk deploy --app "python cdk/app.py"`
- Cambios en infraestructura: `cdk diff --app "python cdk/app.py"` para previsualizar, luego `cdk deploy --app "python cdk/app.py"`

## Ejecutar Tests

```bash
pip install -r backend/requirements-test.txt
python -m pytest backend/tests/ -v
```

## Consideraciones de Costos

Esta solución utiliza varios servicios de AWS que pueden generar costos:

- **Amazon Bedrock** — Se cobra por token de entrada/salida. Aplica el precio de Claude Sonnet 4.5. Cada análisis o generación de política utiliza típicamente entre 1.000 y 3.000 tokens. Ver [precios de Amazon Bedrock](https://aws.amazon.com/bedrock/pricing/).
- **AWS Lambda** — Se cobra por solicitud y duración de cómputo. La capa gratuita incluye 1 millón de solicitudes/mes.
- **Amazon DynamoDB** — Precio bajo demanda para escrituras del registro de auditoría. Costo mínimo para uso típico.
- **Amazon CloudFront** — Se cobra por solicitud y transferencia de datos. La capa gratuita incluye 1 TB/mes.
- **AWS WAFv2** — Se cobra por web ACL, por regla y por millón de solicitudes inspeccionadas.
- **IAM Access Analyzer** — Las llamadas a la API `ValidatePolicy` son gratuitas.

Para una demostración o herramienta interna de bajo tráfico, espere costos inferiores a $5/mes excluyendo el uso de Bedrock. Los costos de Bedrock dependen del volumen de análisis y generaciones de políticas.

## Limpieza

Para eliminar todos los recursos y dejar de incurrir en costos:

```bash
cdk destroy --app "python cdk/app.py"
```

Esto eliminará todos los recursos creados por el stack. Tenga en cuenta que la tabla de auditoría de DynamoDB y el bucket de logs de S3 tienen `RemovalPolicy.RETAIN` y no se eliminarán automáticamente — elimínelos manualmente desde la consola de AWS si ya no los necesita.

## Conclusión

Utilizando Amazon Bedrock e IAM Access Analyzer, es posible construir un portal de autoservicio para evaluar si una política de Amazon IAM cumple con el principio de mínimo privilegio, y para generar nuevas políticas a partir de descripciones en lenguaje natural. La interfaz conversacional permite a los usuarios refinar las políticas iterativamente hasta que cumplan con los requisitos de seguridad, agilizando la interacción entre el área de seguridad y de desarrollo de aplicaciones.

Adicionalmente, es posible modificar esta solución para integrarla en el flujo de solicitud de permisos de su organización, por ejemplo, para rechazar de manera automática las solicitudes que no cumplan con un puntaje mínimo de cumplimiento. Esto permitirá disminuir la lista de tareas pendientes del área de seguridad dejando la interacción humana solo para solicitudes que cumplan con las buenas prácticas.

## Nota

Esta solución es una demostración: El análisis y generación automatizada de políticas debe ser considerado una sugerencia. Antes de implementar cualquier política en su organización, asegúrese de validarla con un especialista en seguridad.


---

Autor: Hernan Fernandez Retamal
