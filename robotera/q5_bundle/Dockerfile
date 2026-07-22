ARG ROS_BASE_IMAGE=ros:humble-ros-base
ARG PYPI_MIRROR=https://pypi.org/simple/
FROM ${ROS_BASE_IMAGE}
ARG PYPI_MIRROR

ENV ROS_DOMAIN_ID=211
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-sensor-msgs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY requirements.txt /work/requirements.txt
RUN pip3 install --no-cache-dir -i ${PYPI_MIRROR} -r requirements.txt

COPY main.py /work/main.py
COPY q5_sdk_client.py /work/q5_sdk_client.py
COPY joint_state.py /work/joint_state.py
COPY robot_ready.py /work/robot_ready.py
COPY config.yaml /work/config.yaml

EXPOSE 15793

CMD ["python3", "main.py"]
