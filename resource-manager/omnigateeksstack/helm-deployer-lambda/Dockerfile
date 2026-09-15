FROM public.ecr.aws/lambda/python:3.12

RUN dnf install -y tar gzip java-17-amazon-corretto-headless && dnf clean all

RUN KUBECTL_VERSION="$(curl -fsSL https://dl.k8s.io/release/stable.txt)" \
    && curl -fsSL -o /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl

RUN curl -fsSL https://get.helm.sh/helm-v3.16.2-linux-amd64.tar.gz -o /tmp/helm.tar.gz \
    && tar -xzf /tmp/helm.tar.gz -C /tmp \
    && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
    && chmod +x /usr/local/bin/helm \
    && rm -rf /tmp/helm.tar.gz /tmp/linux-amd64

RUN pip install boto3

ENV PATH="/usr/local/bin:${PATH}"

COPY handler.py ${LAMBDA_TASK_ROOT}/
COPY storageclass.yaml ${LAMBDA_TASK_ROOT}/
COPY omnigate-chart ${LAMBDA_TASK_ROOT}/omnigate-chart

CMD ["handler.lambda_handler"]
