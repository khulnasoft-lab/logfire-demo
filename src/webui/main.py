from __future__ import annotations as _annotations

from time import time

from fastui import AnyComponent, FastUI
from fastui import components as c
from fastui.events import GoToEvent
from readyapi import APIRouter

from .shared import demo_page

router = APIRouter()


@router.get('/', response_model=FastUI, response_model_exclude_none=True)
def api_index() -> list[AnyComponent]:
    # language=markdown
    markdown = """\
This site demonstrates [Pydantic Logfire](https://docs.logfire.dev).

You can use the sections below to see how different tasks are recorded by Logfire.
"""
    return demo_page(
        c.Markdown(text=markdown),
        c.Div(
            components=[
                c.Heading(text='Table and DB queries', level=2),
                c.Link(
                    components=[c.Text(text='View a table where data is fetched from the database.')],
                    on_click=GoToEvent(url='/table'),
                ),
            ],
            class_name='border-top mt-3 pt-1',
        ),
        c.Div(
            components=[
                c.Heading(text='LLM Query', level=2),
                c.Link(components=[c.Text(text='Simple LLM question and answer.')], on_click=GoToEvent(url='/llm')),
            ],
            class_name='border-top mt-3 pt-1',
        ),
        c.Div(
            components=[
                c.Heading(text='Background Tasks', level=2),
                c.Link(
                    components=[c.Text(text='Use a worker to execute long running tasks.')],
                    on_click=GoToEvent(url='/worker'),
                ),
            ],
            class_name='border-top mt-3 pt-1',
        ),
        c.Div(
            components=[
                c.Heading(text='Distributed Tracing', level=2),
                c.Paragraph(text="Here's an image generated by a separate tiling service."),
                c.Image(src=f'/map.jpg?v={time()}', alt='Map', width=600, height=400),
            ],
            class_name='border-top mt-3 pt-1',
        ),
    )


@router.get('/{path:path}', status_code=404)
async def api_404():
    # so we don't fall through to the index page
    return {'message': 'Not Found'}
