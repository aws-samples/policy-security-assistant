#!/bin/sh
python_v=$(python3 -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')")
python3 -m venv .venv
source .venv/bin/activate
pip3 install boto3==1.28.61
mkdir -p python/lib/python$python_v/site-packages
cp -r .venv/lib/python$python_v/site-packages/* python/lib/python$python_v/site-packages/
zip -r9 ./boto3-layer.zip python

layer_version=$(aws lambda publish-layer-version --layer-name security-assistant --description "Lambda Layer for Security Assistant" --zip-file fileb://boto3-layer.zip --compatible-runtimes python$python_v --query 'LayerVersionArn')

echo "Python Version: $python_v"
echo "Layer ARN: $layer_version"
