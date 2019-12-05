from setuptools import setup, find_packages

setup(
    name='grpc_shell',
    version='0.1',
    author='Martin Tibensky',
    author_email='martin.tibensky@nokia.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 2'
    ],
    package_dir = {'': 'src'},
    packages=find_packages('src'),
    install_requires=[
        'Click<=6.7',
        'click-completion',
        'click-shell',
        'configparser',
        'gnureadline',
        'grpcio',
        'grpcio-tools',
        'protobuf',
        'cryptography'
    ],
    entry_points= {
        'console_scripts': ['grpc_shell = shell.grpc_shell:main'
        ]
    },
)


