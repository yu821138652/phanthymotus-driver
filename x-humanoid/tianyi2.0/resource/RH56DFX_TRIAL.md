# RH56DFX Hand Skeleton Trial

`tianyi2_model.calibrated.urdf` is a byte-for-byte backup of the calibrated
Tianyi skeleton. The production resource remains `tianyi2_model.urdf`.

`tianyi2_model_rh56dfx_trial.urdf` is an opt-in stick-skeleton trial based on
the public community RH56DFX description:

<https://github.com/ookkshirsagar/rh56dfx_description>

It adopts the source model's longer palm/finger proportions and its thumb
flexion chain, while retaining Tianyi's wrist attachment and six real-time
hand feedback channels. This is not an official Inspire calibration.

The web skeleton renderer draws joint-origin cylinders only. It does not load
URDF mesh files or evaluate `<mimic>` elements, so the 50 MB RH56DFX STL set is
intentionally not included. `device.py` explicitly publishes the trial
thumb's two coupled joints.

## Test

Set the following under `plugins.state` in `config.yaml`, rebuild/restart the
test container, then close and reopen the joints card so it reloads the URDF:

```yaml
urdf_model: "tianyi2_model_rh56dfx_trial.urdf"
```

Switch the value back to `tianyi2_model.urdf` to restore the calibrated model.
