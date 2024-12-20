# API Reference

## Discover


```{module} kasa
```

```{eval-rst}
.. autoclass:: Discover
    :members:
```

## Device

% N.B. Credentials clashes with autodoc

```{eval-rst}
.. autoclass:: Device
    :members:
    :undoc-members:
    :exclude-members: Credentials
```


## Device Config


```{eval-rst}
.. autoclass:: Credentials
    :members:
    :undoc-members:
```


```{eval-rst}
.. autoclass:: DeviceConfig
    :members:
    :undoc-members:
```


```{eval-rst}
.. autoclass:: DeviceFamily
    :members:
    :undoc-members:
```

```{eval-rst}
.. autoclass:: DeviceConnectionParameters
    :members:
    :undoc-members:
```

```{eval-rst}
.. autoclass:: DeviceEncryptionType
    :members:
    :undoc-members:
```

## Modules and Features

```{eval-rst}
.. autoclass:: Module
    :members:
```

```{eval-rst}
.. autoclass:: Feature
    :members:
    :inherited-members:
    :undoc-members:
```

```{eval-rst}
.. automodule:: kasa.interfaces
    :members:
    :inherited-members:
    :undoc-members:
```

## Protocols and transports


```{eval-rst}
.. automodule:: kasa.protocols
    :members:
    :imported-members:
    :undoc-members:
    :exclude-members: SmartErrorCode
    :no-index:
```

```{eval-rst}
.. automodule:: kasa.transports
    :members:
    :imported-members:
    :undoc-members:
    :no-index:
```


## Errors and exceptions



```{eval-rst}
.. autoclass:: kasa.exceptions.KasaException
    :members:
    :undoc-members:
```

```{eval-rst}
.. autoclass:: kasa.exceptions.DeviceError
    :members:
    :undoc-members:
```

```{eval-rst}
.. autoclass:: kasa.exceptions.AuthenticationError
    :members:
    :undoc-members:
```

```{eval-rst}
.. autoclass:: kasa.exceptions.UnsupportedDeviceError
    :members:
    :undoc-members:
```

```{eval-rst}
.. autoclass:: kasa.exceptions.TimeoutError
    :members:
    :undoc-members:
```
