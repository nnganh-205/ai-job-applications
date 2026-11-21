"""Presentation-only CV designs; data keys remain the common CVDocument contract."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

SectionKey = Literal['summary', 'education', 'experience', 'project', 'skills',
                     'certifications', 'awards', 'references', 'involvement']
SECTION_KEYS = ['summary', 'education', 'experience', 'project', 'skills',
                'certifications', 'awards', 'references', 'involvement']


class TemplateDesign(BaseModel):
    model_config = ConfigDict(extra='forbid')
    layout: Literal['one-column', 'two-column'] = 'one-column'
    sidebar_position: Literal['left', 'right'] = 'left'
    sidebar_width: int = Field(default=32, ge=25, le=40)
    header_align: Literal['left', 'center'] = 'left'
    heading_style: Literal['line', 'filled', 'plain'] = 'line'
    show_photo: bool = False
    photo_shape: Literal['circle', 'square'] = 'circle'
    margin_mm: int = Field(default=16, ge=10, le=24)
    section_gap: int = Field(default=14, ge=8, le=24)
    main_sections: list[SectionKey] = Field(default_factory=lambda: list(SECTION_KEYS))
    sidebar_sections: list[SectionKey] = Field(default_factory=list)

    @model_validator(mode='after')
    def preserve_data_sections(self):
        keys = self.main_sections + self.sidebar_sections
        if len(keys) != len(SECTION_KEYS) or set(keys) != set(SECTION_KEYS):
            raise ValueError('Mỗi nhóm dữ liệu phải xuất hiện đúng một lần trong bố cục.')
        if not self.main_sections:
            raise ValueError('Cột chính cần có ít nhất một nhóm dữ liệu.')
        if self.layout == 'one-column' and self.sidebar_sections:
            raise ValueError('Bố cục một cột không có nhóm dữ liệu ở cột phụ.')
        return self
