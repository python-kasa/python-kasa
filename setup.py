from setuptools import setup

setup(name='pyHS100',
      version='0.3.0',
      description='Interface for TPLink HS100 Smart Plugs.',
      url='https://github.com/GadgetReactor/pyHS100',
      author='Sean Seah (GadgetReactor)',
      author_email='sean@gadgetreactor.com',
      license='GPLv3',
      packages=['pyHS100'],
      install_requires=['click', 'click-datetime', 'typing'],
      entry_points={
            'console_scripts': [
                  'pyhs100=pyHS100.cli:cli',
            ],
      },
      zip_safe=False)
