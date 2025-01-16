from setuptools import setup, find_packages

setup(
    name="hexaa_business_scraper",
    version="0.1.0",
    description="A web scraping library and API for Google Maps",
    packages=find_packages(),
    install_requires=[
        "flask",
        "flask_cors",
        "playwright",
        "pandas"
    ],
    entry_points={
        'console_scripts': [
            'hexaa_business_scraper=hexaa_scraper.app:app.run',
        ]
    },
)
