"""Stable template IDs shared by CV and resume presentation schemas."""
from typing import Annotated, Literal
from pydantic import Field

BuiltinTemplateID = Literal[
    'simple',
    'clean',
    'minimal',
    'compact',
    'executive',
    'corporate',
    'consultant',
    'precision',
    'modern',
    'sidebar',
    'metro',
    'split',
    'creative',
    'editorial',
    'banner',
    'accent',
    'classic',
    'academic',
    'harvard',
    'harvard-compact',
    'ats',
    'ats-jake',
    'ats-technical',
    'ats-graduate',
]

TemplateID = BuiltinTemplateID | Annotated[str, Field(pattern=r'^custom_[a-f0-9]{32}$')]
