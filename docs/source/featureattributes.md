Some modules have attributes that may not be supported by the device.
These attributes will be annotated with a `FeatureAttribute` return type.
For example:

```py
    @property
    def hsv(self) -> Annotated[HSV, FeatureAttribute()]:
        """Return the current HSV state of the bulb."""
```

You can test whether a `FeatureAttribute` is supported by the device with {meth}`kasa.Module.has_feature`
or {meth}`kasa.Module.get_feature` which will return `None` if not supported.
Calling these methods on attributes not annotated with a `FeatureAttribute` return type will return an error.
