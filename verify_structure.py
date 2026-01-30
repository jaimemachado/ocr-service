#!/usr/bin/env python3
"""
Verify that the service structure is complete
"""
import os
import ast

def check_file_exists(filepath, description):
    """Check if a file exists"""
    exists = os.path.exists(filepath)
    status = "✓" if exists else "✗"
    print(f"{status} {description}: {filepath}")
    return exists

def check_python_syntax(filepath):
    """Check if Python file has valid syntax"""
    try:
        with open(filepath, 'r') as f:
            ast.parse(f.read())
        print(f"✓ Valid Python syntax: {filepath}")
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error in {filepath}: {e}")
        return False

def check_function_exists(filepath, function_name):
    """Check if a function exists in a Python file"""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        exists = function_name in functions
        status = "✓" if exists else "✗"
        print(f"{status} Function '{function_name}' in {filepath}")
        return exists
    except Exception as e:
        print(f"✗ Error checking {filepath}: {e}")
        return False

def main():
    """Main verification"""
    print("=" * 60)
    print("OCR Service Structure Verification")
    print("=" * 60)
    
    checks = []
    
    # Check required files
    print("\n📁 Checking files...")
    checks.append(check_file_exists("main.py", "Main application"))
    checks.append(check_file_exists("requirements.txt", "Requirements file"))
    checks.append(check_file_exists("Dockerfile", "Dockerfile"))
    checks.append(check_file_exists("docker-compose.yml", "Docker Compose"))
    checks.append(check_file_exists("README.md", "README"))
    checks.append(check_file_exists(".gitignore", "Git ignore"))
    checks.append(check_file_exists("test_main.py", "Tests"))
    checks.append(check_file_exists("example.py", "Example script"))
    
    # Check Python syntax
    print("\n🐍 Checking Python syntax...")
    checks.append(check_python_syntax("main.py"))
    checks.append(check_python_syntax("test_main.py"))
    checks.append(check_python_syntax("example.py"))
    
    # Check key functions in main.py
    print("\n🔧 Checking main.py functions...")
    checks.append(check_function_exists("main.py", "root"))
    checks.append(check_function_exists("main.py", "health"))
    checks.append(check_function_exists("main.py", "process_pdf"))
    checks.append(check_function_exists("main.py", "extract_text"))
    checks.append(check_function_exists("main.py", "pdf_to_images"))
    checks.append(check_function_exists("main.py", "run_ocr_on_images"))
    checks.append(check_function_exists("main.py", "embed_text_layer"))
    
    # Check requirements
    print("\n📦 Checking requirements.txt...")
    with open("requirements.txt", 'r') as f:
        requirements = f.read()
        required_packages = ["fastapi", "uvicorn", "pdf2image", "python-doctr", "ocrmypdf"]
        for pkg in required_packages:
            exists = pkg in requirements
            status = "✓" if exists else "✗"
            print(f"{status} Package '{pkg}' in requirements.txt")
            checks.append(exists)
    
    # Summary
    print("\n" + "=" * 60)
    passed = sum(checks)
    total = len(checks)
    print(f"Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("✓ All checks passed! Service structure is complete.")
        return 0
    else:
        print("✗ Some checks failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    exit(main())
