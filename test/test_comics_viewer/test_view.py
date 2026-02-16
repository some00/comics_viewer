import pytest
from typing import Callable
from comics_viewer.view import View
from dataclasses import dataclass, fields
from OpenGL.arrays.vbo import VBO


@dataclass(frozen=True)
class MockOGL:
    glGenVertexArrays: Callable
    glBindVertexArray: Callable
    glDeleteVertexArrays: Callable
    glDeleteShader: Callable
    glDeleteProgram: Callable
    glGenTextures: Callable
    glBindTexture: Callable
    glTexParameteri: Callable
    glTexImage2D: Callable
    glGenerateMipmap: Callable
    glDeleteTextures: Callable
    glClearColor: Callable
    glClear: Callable
    glGetIntegeri_v: Callable
    glUniformMatrix4fv: Callable
    glDrawElements: Callable
    glFlush: Callable
    glPixelStorei: Callable
    glVertexAttribPointer: Callable
    glEnableVertexAttribArray: Callable
    glGetUniformLocation: Callable


@pytest.fixture
def ogl(mocker) -> MockOGL:
    kwargs = {}
    for field in fields(MockOGL):
        kwargs[field.name] = mocker.patch(
                f"comics_viewer.view.OGL.{field.name}")
    return MockOGL(**kwargs)


@pytest.fixture
def vbo(mocker) -> VBO:
    return mocker.patch("comics_viewer.view.vbo.VBO", spec=VBO)


@dataclass(frozen=True)
class MockShaders:
    compileShader: Callable
    compileProgram: Callable


@pytest.fixture
def shaders(mocker) -> MockShaders:
    return MockShaders(
        compileProgram=mocker.patch(
            "comics_viewer.view.shaders.compileProgram"),
        compileShader=mocker.patch(
            "comics_viewer.view.shaders.compileShader"),
    )
