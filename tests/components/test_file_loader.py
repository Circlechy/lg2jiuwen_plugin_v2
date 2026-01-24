"""
文件加载组件单元测试
"""
import os
import tempfile
import pytest

from lg2jiuwen_tool.components.file_loader import FileLoaderComp


class TestFileLoaderComp:
    """文件加载组件测试"""

    def setup_method(self):
        self.comp = FileLoaderComp()

    @pytest.mark.asyncio
    async def test_load_single_file(self):
        """测试加载单个文件"""
        content = '''
def hello():
    print("Hello, World!")

if __name__ == "__main__":
    hello()
'''
        with tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w') as f:
            f.write(content)
            temp_file = f.name

        try:
            result = await self.comp.invoke(
                inputs={
                    "file_list": [temp_file],
                    "dependency_order": [temp_file]
                },
                runtime=None,
                context=None
            )
            assert "file_contents" in result
            assert temp_file in result["file_contents"]
            assert "hello" in result["file_contents"][temp_file]
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_load_multiple_files(self):
        """测试加载多个文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            files = {}
            for name, content in [
                ('a.py', 'def func_a(): pass'),
                ('b.py', 'def func_b(): pass'),
                ('c.py', 'def func_c(): pass'),
            ]:
                path = os.path.join(temp_dir, name)
                with open(path, 'w') as f:
                    f.write(content)
                files[path] = content

            result = await self.comp.invoke(
                inputs={
                    "file_list": list(files.keys()),
                    "dependency_order": list(files.keys())
                },
                runtime=None,
                context=None
            )
            assert "file_contents" in result
            assert len(result["file_contents"]) == 3
            for path, expected_content in files.items():
                assert result["file_contents"][path] == expected_content

    @pytest.mark.asyncio
    async def test_load_utf8_file(self):
        """测试加载 UTF-8 编码文件"""
        content = '''
# 中文注释
def 你好():
    return "世界"
'''
        with tempfile.NamedTemporaryFile(
            suffix='.py', delete=False, mode='w', encoding='utf-8'
        ) as f:
            f.write(content)
            temp_file = f.name

        try:
            result = await self.comp.invoke(
                inputs={
                    "file_list": [temp_file],
                    "dependency_order": [temp_file]
                },
                runtime=None,
                context=None
            )
            assert "中文注释" in result["file_contents"][temp_file]
            assert "你好" in result["file_contents"][temp_file]
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_load_nonexistent_file(self):
        """测试加载不存在的文件"""
        result = await self.comp.invoke(
            inputs={
                "file_list": ["/nonexistent/file.py"],
                "dependency_order": ["/nonexistent/file.py"]
            },
            runtime=None,
            context=None
        )
        # 应该返回空或包含错误信息
        assert "file_contents" in result
        file_contents = result["file_contents"]
        if file_contents:
            # 可能包含错误标记或为空
            pass

    @pytest.mark.asyncio
    async def test_preserve_dependency_order(self):
        """测试保持依赖顺序"""
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = []
            for name in ['z.py', 'a.py', 'm.py']:
                path = os.path.join(temp_dir, name)
                with open(path, 'w') as f:
                    f.write(f'# {name}\n')
                paths.append(path)

            # 指定特定顺序
            order = [paths[1], paths[2], paths[0]]  # a.py, m.py, z.py

            result = await self.comp.invoke(
                inputs={
                    "file_list": paths,
                    "dependency_order": order
                },
                runtime=None,
                context=None
            )
            assert result["dependency_order"] == order
