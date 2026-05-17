#!/usr/bin/env python3
"""
───────────────────────────────────────────────────────────────────────────────
                         G — GLANG  v0.2
───────────────────────────────────────────────────────────────────────────────

Inspired By:  Python · Lua · C
File ext:     .g
Run:          python3 g.py <file.g>
              python3 g.py              (REPL)
              python3 g.py --install <git-url>
───────────────────────────────────────────────────────────────────────────────
"""

import sys, re, os, ctypes, math, time, json, random, subprocess, shutil

# ─────────────────────────────────────────────────────────────────────────────
#  PACKAGE PATHS
#  ~/.glang/packages  is the global install root.
#  A local  ./packages  directory is also searched first.
# ─────────────────────────────────────────────────────────────────────────────
_HOME_PKG  = os.path.join(os.path.expanduser("~"), ".glang", "packages")
_LOCAL_PKG = os.path.join(os.getcwd(), "packages")
os.makedirs(_HOME_PKG, exist_ok=True)

# ═════════════════════════════════════════════════════════════════════════════
#  TOKENS
# ═════════════════════════════════════════════════════════════════════════════
KEYWORDS = {
    'let','set','if','else','elif','while','for','in','func','return',
    'pass','continue','break','with','as','class','new','import',
    'true','false','null','and','or','not',
}

class Token:
    __slots__ = ('kind','value','line')
    def __init__(self, kind, value, line):
        self.kind = kind; self.value = value; self.line = line
    def __repr__(self):
        return f'Token({self.kind}, {self.value!r}, L{self.line})'

# ═════════════════════════════════════════════════════════════════════════════
#  LEXER
# ═════════════════════════════════════════════════════════════════════════════
class LexError(Exception): pass

class Lexer:
    def __init__(self, src):
        self.src = src; self.pos = 0; self.line = 1

    def peek(self, offset=0):
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else ''

    def advance(self):
        ch = self.src[self.pos]; self.pos += 1
        if ch == '\n': self.line += 1
        return ch

    def match(self, ch):
        if self.pos < len(self.src) and self.src[self.pos] == ch:
            self.pos += 1; return True
        return False

    def skip(self):
        while self.pos < len(self.src):
            ch = self.peek()
            if ch in ' \t\r\n':
                self.advance()
            elif ch == '/' and self.peek(1) == '/':
                while self.pos < len(self.src) and self.peek() != '\n': self.advance()
            elif ch == '/' and self.peek(1) == '*':
                self.advance(); self.advance()
                while self.pos < len(self.src):
                    if self.peek() == '*' and self.peek(1) == '/':
                        self.advance(); self.advance(); break
                    self.advance()
            else: break

    def read_string(self, quote):
        self.advance()
        buf = []
        while self.pos < len(self.src):
            ch = self.peek()
            if ch == '\\':
                self.advance(); esc = self.advance()
                buf.append({'n':'\n','t':'\t','r':'\r','\\':'\\',
                            '"':'"',"'":'\'','0':'\0'}.get(esc, esc))
            elif ch == quote:
                self.advance(); break
            else:
                buf.append(self.advance())
        return ''.join(buf)

    def tokenize(self):
        tokens = []
        TWO = {
            '**':'STARSTAR','==':'EQ','!=':'NEQ','<=':'LTE','>=':'GTE',
            '&&':'AND','||':'OR','+=':'PLUSEQ','-=':'MINUSEQ',
            '*=':'STAREQ','/=':'SLASHEQ','->':'ARROW',
        }
        ONE = {
            '+':'PLUS','-':'MINUS','*':'STAR','/':'SLASH','%':'PERCENT',
            '=':'ASSIGN','<':'LT','>':'GT','!':'NOT',
            '(':'LPAREN',')':'RPAREN','{':'LBRACE','}':'RBRACE',
            '[':'LBRACK',']':'RBRACK',',':'COMMA','.':'DOT',
            ';':'SEMI',':':'COLON',
        }
        while True:
            self.skip()
            if self.pos >= len(self.src):
                tokens.append(Token('EOF','',self.line)); break
            ln = self.line; ch = self.peek()

            if ch in ('"',"'"):
                tokens.append(Token('STRING', self.read_string(ch), ln)); continue

            if ch.isdigit() or (ch == '.' and self.peek(1).isdigit()):
                buf = []
                while self.pos < len(self.src) and (self.peek().isdigit() or self.peek() == '.'):
                    buf.append(self.advance())
                raw = ''.join(buf)
                val = float(raw) if '.' in raw else int(raw)
                tokens.append(Token('NUMBER', val, ln)); continue

            if ch.isalpha() or ch == '_':
                buf = []
                while self.pos < len(self.src) and (self.peek().isalnum() or self.peek() == '_'):
                    buf.append(self.advance())
                word = ''.join(buf)
                if   word == 'true':  tokens.append(Token('BOOL',  True,  ln))
                elif word == 'false': tokens.append(Token('BOOL',  False, ln))
                elif word == 'null':  tokens.append(Token('NULL',  None,  ln))
                elif word == 'and':   tokens.append(Token('AND',   '&&',  ln))
                elif word == 'or':    tokens.append(Token('OR',    '||',  ln))
                elif word == 'not':   tokens.append(Token('NOT',   '!',   ln))
                elif word in KEYWORDS: tokens.append(Token(word.upper(), word, ln))
                else:                  tokens.append(Token('IDENT', word, ln))
                continue

            two = ch + self.peek(1)
            if two in TWO:
                self.advance(); self.advance()
                tokens.append(Token(TWO[two], two, ln)); continue

            if ch in ONE:
                self.advance()
                tokens.append(Token(ONE[ch], ch, ln)); continue

            raise LexError(f"Unexpected character {ch!r} at line {ln}")
        return tokens

# ═════════════════════════════════════════════════════════════════════════════
#  AST
# ═════════════════════════════════════════════════════════════════════════════
class Node: pass

class Block(Node):
    def __init__(self, stmts): self.stmts = stmts

class LetStmt(Node):
    def __init__(self, name, value, line): self.name=name; self.value=value; self.line=line

class AssignStmt(Node):
    def __init__(self, target, op, value, line): self.target=target; self.op=op; self.value=value; self.line=line

class SetStmt(Node):
    """set x = expr  — must already exist, updates in-place up the scope chain"""
    def __init__(self, target, value, line): self.target=target; self.value=value; self.line=line

class IfStmt(Node):
    def __init__(self, branches, else_block): self.branches=branches; self.else_block=else_block

class WhileStmt(Node):
    def __init__(self, cond, body): self.cond=cond; self.body=body

class ForStmt(Node):
    def __init__(self, var, iterable, body): self.var=var; self.iterable=iterable; self.body=body

class FuncDef(Node):
    def __init__(self, name, params, body, line): self.name=name; self.params=params; self.body=body; self.line=line

class ReturnStmt(Node):
    def __init__(self, value, line): self.value=value; self.line=line

class PassStmt(Node): pass
class ContinueStmt(Node): pass
class BreakStmt(Node): pass

class WithStmt(Node):
    def __init__(self, call, alias, body): self.call=call; self.alias=alias; self.body=body

class ClassDef(Node):
    def __init__(self, name, base, body): self.name=name; self.base=base; self.body=body

class ImportStmt(Node):
    def __init__(self, path, alias, is_pkg=False): self.path=path; self.alias=alias; self.is_pkg=is_pkg

class ExprStmt(Node):
    def __init__(self, expr): self.expr=expr

# expressions
class NumberLit(Node):
    def __init__(self, v): self.v=v
class StringLit(Node):
    def __init__(self, v): self.v=v
class BoolLit(Node):
    def __init__(self, v): self.v=v
class NullLit(Node): pass
class Ident(Node):
    def __init__(self, name, line): self.name=name; self.line=line
class BinOp(Node):
    def __init__(self, op, left, right): self.op=op; self.left=left; self.right=right
class UnaryOp(Node):
    def __init__(self, op, expr): self.op=op; self.expr=expr
class Call(Node):
    def __init__(self, callee, args, line): self.callee=callee; self.args=args; self.line=line
class GetAttr(Node):
    def __init__(self, obj, attr, line): self.obj=obj; self.attr=attr; self.line=line
class SetAttr(Node):
    def __init__(self, obj, attr, value): self.obj=obj; self.attr=attr; self.value=value
class Index(Node):
    def __init__(self, obj, idx, line): self.obj=obj; self.idx=idx; self.line=line
class SetIndex(Node):
    def __init__(self, obj, idx, value): self.obj=obj; self.idx=idx; self.value=value
class ListLit(Node):
    def __init__(self, items): self.items=items
class DictLit(Node):
    def __init__(self, pairs): self.pairs=pairs
class NewExpr(Node):
    def __init__(self, cls, args, line): self.cls=cls; self.args=args; self.line=line
class LambdaExpr(Node):
    def __init__(self, params, body): self.params=params; self.body=body

# ═════════════════════════════════════════════════════════════════════════════
#  PARSER
# ═════════════════════════════════════════════════════════════════════════════
class ParseError(Exception): pass

class Parser:
    def __init__(self, tokens): self.tokens=tokens; self.pos=0

    def peek(self, offset=0):
        i = self.pos + offset
        return self.tokens[i] if i < len(self.tokens) else self.tokens[-1]

    def advance(self): t=self.tokens[self.pos]; self.pos+=1; return t
    def check(self, *kinds): return self.peek().kind in kinds
    def match(self, *kinds):
        if self.check(*kinds): return self.advance()
        return None
    def expect(self, kind, msg=None):
        if self.peek().kind == kind: return self.advance()
        t = self.peek()
        raise ParseError(msg or f"Expected {kind!r}, got {t.kind!r} ({t.value!r}) at line {t.line}")

    def parse(self):
        stmts = []
        while not self.check('EOF'): stmts.append(self.parse_stmt())
        return Block(stmts)

    def parse_block(self):
        self.expect('LBRACE')
        stmts = []
        while not self.check('RBRACE','EOF'): stmts.append(self.parse_stmt())
        self.expect('RBRACE')
        return Block(stmts)

    def parse_stmt(self):
        self.match('SEMI')
        t = self.peek()
        if t.kind == 'LET':      return self.parse_let()
        if t.kind == 'SET':      return self.parse_set()
        if t.kind == 'IF':       return self.parse_if()
        if t.kind == 'WHILE':    return self.parse_while()
        if t.kind == 'FOR':      return self.parse_for()
        if t.kind == 'FUNC':     return self.parse_func()
        if t.kind == 'RETURN':   return self.parse_return()
        if t.kind == 'PASS':     self.advance(); return PassStmt()
        if t.kind == 'CONTINUE': self.advance(); return ContinueStmt()
        if t.kind == 'BREAK':    self.advance(); return BreakStmt()
        if t.kind == 'WITH':     return self.parse_with()
        if t.kind == 'CLASS':    return self.parse_class()
        if t.kind == 'IMPORT':   return self.parse_import()
        return self.parse_assign_or_expr()

    def parse_let(self):
        ln = self.peek().line; self.expect('LET')
        name = self.expect('IDENT').value
        self.expect('ASSIGN'); val = self.parse_expr()
        self.match('SEMI')
        return LetStmt(name, val, ln)

    def parse_set(self):
        ln = self.peek().line; self.expect('SET')
        name = self.expect('IDENT').value
        self.expect('ASSIGN'); val = self.parse_expr()
        self.match('SEMI')
        return SetStmt(name, val, ln)

    def parse_assign_or_expr(self):
        expr = self.parse_expr()
        op_map = {'ASSIGN':'=','PLUSEQ':'+=','MINUSEQ':'-=','STAREQ':'*=','SLASHEQ':'/='}
        if self.peek().kind in op_map:
            op = op_map[self.advance().kind]
            val = self.parse_expr(); self.match('SEMI')
            if isinstance(expr, Ident):
                return AssignStmt(expr.name, op, val, expr.line)
            if isinstance(expr, GetAttr): return SetAttr(expr.obj, expr.attr, val)
            if isinstance(expr, Index):   return SetIndex(expr.obj, expr.idx, val)
            raise ParseError("Invalid assignment target")
        self.match('SEMI')
        return ExprStmt(expr)

    def parse_if(self):
        self.expect('IF'); self.expect('LPAREN')
        cond = self.parse_expr(); self.expect('RPAREN')
        body = self.parse_block(); branches = [(cond, body)]; else_block = None
        while self.check('ELIF'):
            self.advance(); self.expect('LPAREN')
            c2 = self.parse_expr(); self.expect('RPAREN')
            b2 = self.parse_block(); branches.append((c2, b2))
        if self.match('ELSE'): else_block = self.parse_block()
        return IfStmt(branches, else_block)

    def parse_while(self):
        self.expect('WHILE'); self.expect('LPAREN')
        cond = self.parse_expr(); self.expect('RPAREN')
        return WhileStmt(cond, self.parse_block())

    def parse_for(self):
        self.expect('FOR'); self.expect('LPAREN')
        var = self.expect('IDENT').value; self.expect('IN')
        iterable = self.parse_expr(); self.expect('RPAREN')
        return ForStmt(var, iterable, self.parse_block())

    def parse_func(self):
        ln = self.peek().line; self.expect('FUNC')
        name = self.expect('IDENT').value
        self.expect('LPAREN')
        params = []
        while not self.check('RPAREN','EOF'):
            params.append(self.expect('IDENT').value)
            if not self.match('COMMA'): break
        self.expect('RPAREN')
        return FuncDef(name, params, self.parse_block(), ln)

    def parse_return(self):
        ln = self.peek().line; self.expect('RETURN')
        val = None
        if not self.check('SEMI','RBRACE','EOF'): val = self.parse_expr()
        self.match('SEMI')
        return ReturnStmt(val, ln)

    def parse_with(self):
        self.expect('WITH'); self.expect('LPAREN')
        call = self.parse_expr(); self.expect('RPAREN')
        self.expect('AS'); alias = self.expect('IDENT').value
        return WithStmt(call, alias, self.parse_block())

    def parse_class(self):
        self.expect('CLASS'); name = self.expect('IDENT').value
        base = None
        if self.match('LPAREN'):
            base = self.expect('IDENT').value; self.expect('RPAREN')
        return ClassDef(name, base, self.parse_block())

    def parse_import(self):
        """
        Supported forms:
          import <"packages.g.os">      <- angle-bracket package import
          import <"g.os">
          import mymod                  <- bare ident (relative .g file)
          import mymod as m
        """
        self.expect('IMPORT')
        alias = None; is_pkg = False
        if self.match('LT'):
            path = self.expect('STRING').value
            self.expect('GT')
            is_pkg = True
        else:
            parts = [self.expect('IDENT').value]
            while self.match('DOT'):
                parts.append(self.expect('IDENT').value)
            path = '.'.join(parts)
        if self.match('AS'): alias = self.expect('IDENT').value
        self.match('SEMI')
        return ImportStmt(path, alias, is_pkg)

    # ── expressions ───────────────────────────────────────────────────────────
    def parse_expr(self):    return self.parse_or()
    def parse_or(self):
        l = self.parse_and()
        while self.check('OR'):
            self.advance(); l = BinOp('||', l, self.parse_and())
        return l
    def parse_and(self):
        l = self.parse_equality()
        while self.check('AND'):
            self.advance(); l = BinOp('&&', l, self.parse_equality())
        return l
    def parse_equality(self):
        l = self.parse_comparison()
        while self.check('EQ','NEQ'):
            op = self.advance().value; l = BinOp(op, l, self.parse_comparison())
        return l
    def parse_comparison(self):
        l = self.parse_add()
        while self.check('LT','GT','LTE','GTE'):
            op = self.advance().value; l = BinOp(op, l, self.parse_add())
        return l
    def parse_add(self):
        l = self.parse_mul()
        while self.check('PLUS','MINUS'):
            op = self.advance().value; l = BinOp(op, l, self.parse_mul())
        return l
    def parse_mul(self):
        l = self.parse_power()
        while self.check('STAR','SLASH','PERCENT'):
            op = self.advance().value; l = BinOp(op, l, self.parse_power())
        return l
    def parse_power(self):
        l = self.parse_unary()
        if self.check('STARSTAR'):
            self.advance(); return BinOp('**', l, self.parse_power())
        return l
    def parse_unary(self):
        if self.check('NOT','MINUS'):
            op = self.advance().value; return UnaryOp(op, self.parse_unary())
        return self.parse_postfix()
    def parse_postfix(self):
        expr = self.parse_primary()
        while True:
            if self.check('DOT'):
                ln = self.peek().line; self.advance()
                attr = self.expect('IDENT').value
                if self.check('LPAREN'):
                    args = self.parse_arglist()
                    expr = Call(GetAttr(expr, attr, ln), args, ln)
                else:
                    expr = GetAttr(expr, attr, ln)
            elif self.check('LPAREN'):
                ln = self.peek().line; args = self.parse_arglist()
                expr = Call(expr, args, ln)
            elif self.check('LBRACK'):
                ln = self.peek().line; self.advance()
                idx = self.parse_expr(); self.expect('RBRACK')
                expr = Index(expr, idx, ln)
            else: break
        return expr
    def parse_arglist(self):
        self.expect('LPAREN'); args = []
        while not self.check('RPAREN','EOF'):
            args.append(self.parse_expr())
            if not self.match('COMMA'): break
        self.expect('RPAREN'); return args
    def parse_primary(self):
        t = self.peek()
        if t.kind == 'NUMBER': self.advance(); return NumberLit(t.value)
        if t.kind == 'STRING': self.advance(); return StringLit(t.value)
        if t.kind == 'BOOL':   self.advance(); return BoolLit(t.value)
        if t.kind == 'NULL':   self.advance(); return NullLit()
        if t.kind == 'IDENT':  self.advance(); return Ident(t.value, t.line)
        if t.kind == 'NEW':
            self.advance(); cls = self.expect('IDENT').value
            return NewExpr(cls, self.parse_arglist(), t.line)
        if t.kind == 'LPAREN':
            self.advance(); e = self.parse_expr(); self.expect('RPAREN'); return e
        if t.kind == 'LBRACK':
            self.advance(); items = []
            while not self.check('RBRACK','EOF'):
                items.append(self.parse_expr())
                if not self.match('COMMA'): break
            self.expect('RBRACK'); return ListLit(items)
        if t.kind == 'LBRACE':
            self.advance(); pairs = []
            while not self.check('RBRACE','EOF'):
                k = self.parse_expr(); self.expect('COLON'); v = self.parse_expr()
                pairs.append((k,v))
                if not self.match('COMMA'): break
            self.expect('RBRACE'); return DictLit(pairs)
        if t.kind == 'FUNC':
            self.advance(); self.expect('LPAREN'); params = []
            while not self.check('RPAREN','EOF'):
                params.append(self.expect('IDENT').value)
                if not self.match('COMMA'): break
            self.expect('RPAREN')
            if self.check('ARROW'): self.advance(); body = self.parse_expr()
            else: body = self.parse_block()
            return LambdaExpr(params, body)
        raise ParseError(f"Unexpected token {t.kind!r} ({t.value!r}) at line {t.line}")

# ═════════════════════════════════════════════════════════════════════════════
#  RUNTIME VALUES
# ═════════════════════════════════════════════════════════════════════════════
class GIFunction:
    def __init__(self, name, params, body, closure):
        self.name=name; self.params=params; self.body=body; self.closure=closure
    def __repr__(self): return f'<func {self.name}>'

class GIClass:
    def __init__(self, name, base, methods, env):
        self.name=name; self.base=base; self.methods=methods; self.env=env
    def __repr__(self): return f'<class {self.name}>'

class GIInstance:
    def __init__(self, klass): self.klass=klass; self.fields={}
    def get(self, name):
        if name in self.fields: return self.fields[name]
        k = self.klass
        while k:
            if name in k.methods: return BoundMethod(self, k.methods[name])
            k = k.base
        raise RuntimeError_(f"No attribute '{name}' on {self.klass.name}")
    def set(self, name, val): self.fields[name]=val
    def __repr__(self): return f'<{self.klass.name} instance>'

class BoundMethod:
    def __init__(self, instance, func): self.instance=instance; self.func=func
    def __repr__(self): return f'<bound {self.func.name}>'

class GILib:
    """Wraps a ctypes library so cbox.loadlib() / loadlib() works."""
    def __init__(self, name, lib): self.name=name; self.lib=lib
    def __repr__(self): return f'<lib {self.name!r}>'

# ─── signals ──────────────────────────────────────────────────────────────────
class ReturnSignal(Exception):
    def __init__(self, val): self.val=val
class ContinueSignal(Exception): pass
class BreakSignal(Exception): pass
class RuntimeError_(Exception): pass

# ═════════════════════════════════════════════════════════════════════════════
#  ENVIRONMENT
# ═════════════════════════════════════════════════════════════════════════════
class Env:
    def __init__(self, parent=None): self.vars={}; self.parent=parent

    def get(self, name, line=None):
        if name in self.vars: return self.vars[name]
        if self.parent: return self.parent.get(name, line)
        raise RuntimeError_(f"Undefined variable '{name}'" + (f" at line {line}" if line else ""))

    def define(self, name, val):
        self.vars[name] = val  # always writes to current scope

    def set(self, name, val):
        """Assign existing variable anywhere in chain, or create locally."""
        if name in self.vars: self.vars[name]=val; return
        if self.parent and self.parent.has(name): self.parent.set(name, val); return
        self.vars[name]=val

    def update(self, name, val, line=None):
        """set-statement: variable MUST already exist somewhere in the chain."""
        if name in self.vars: self.vars[name]=val; return
        if self.parent and self.parent.has(name): self.parent.update(name, val, line); return
        raise RuntimeError_(f"Undefined variable '{name}'" + (f" at line {line}" if line else ""))

    def has(self, name):
        if name in self.vars: return True
        return self.parent.has(name) if self.parent else False

# ═════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════════════════════
def gi_str(val):
    if val is None:  return "null"
    if val is True:  return "true"
    if val is False: return "false"
    if isinstance(val, float) and val == int(val): return str(int(val))
    if isinstance(val, list): return "[" + ", ".join(gi_str(v) for v in val) + "]"
    if isinstance(val, dict): return "{" + ", ".join(f"{gi_str(k)}: {gi_str(v)}" for k,v in val.items()) + "}"
    return str(val)

def _gi_system(*parts):
    """Run a real shell command.  system("echo ", val)  →  echo val"""
    cmd = ''.join(gi_str(p) for p in parts)
    return subprocess.call(cmd, shell=True)

def _gi_loadlib(name):
    """Load a native library via ctypes and return a GILib wrapper."""
    try:
        if sys.platform == 'win32':
            lib = ctypes.WinDLL(name)
        else:
            try:
                lib = ctypes.CDLL(name)
            except OSError:
                lib = ctypes.CDLL(f"lib{name}.so")
        return GILib(name, lib)
    except OSError as e:
        raise RuntimeError_(f"loadlib('{name}') failed: {e}")

# ═════════════════════════════════════════════════════════════════════════════
#  IMPORT RESOLVER
# ═════════════════════════════════════════════════════════════════════════════
def _resolve_import(path: str, is_pkg: bool, current_dir: str):
    """
    Resolves an import path to an absolute .gi file path.

    Search order:
      1. Relative to current script dir (plain imports)
      2. ./packages/<dot-to-slash>.gi
      3. ~/.glang/packages/<dot-to-slash>.gi
      4. Directory package with main.gi / __init__.gi inside those roots
    """
    norm = path.strip()
    if norm.endswith('.g'): norm = norm[:-2]
    # Split on  .  /  \  — filter empty segments
    parts = [p for p in re.split(r'[./\\]+', norm) if p]
    if not parts: return None

    rel_path = os.path.join(*parts) + '.g'
    candidates = []

    if not is_pkg:
        # Bare import → look next to the calling script and CWD
        candidates += [
            os.path.join(current_dir, rel_path),
            os.path.join(os.getcwd(), rel_path),
        ]

    # Package-style roots
    for base in [_LOCAL_PKG, _HOME_PKG]:
        candidates.append(os.path.join(base, rel_path))

    # Directory packages: packages/g/os/main.gi or __init__.gi
    dir_parts = os.path.join(*parts)
    for base in [_LOCAL_PKG, _HOME_PKG]:
        d = os.path.join(base, dir_parts)
        candidates += [
            os.path.join(d, 'main.g'),
            os.path.join(d, '__init__.g'),
        ]

    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None

# ═════════════════════════════════════════════════════════════════════════════
#  INTERPRETER
# ═════════════════════════════════════════════════════════════════════════════
class Interpreter:
    def __init__(self, script_dir: str = '.'):
        self.globals    = Env()
        self.script_dir = os.path.abspath(script_dir)
        self._mod_cache: dict = {}   # abs_file_path → exported dict
        self._setup_builtins()

    # ─────────────────────────────────────────────────────────────────────────
    #  BUILTINS
    # ─────────────────────────────────────────────────────────────────────────
    def _setup_builtins(self):
        g = self.globals

        # ── I/O ───────────────────────────────────────────────────────────────
        #CNLSTDOUT (CNL = Create New Line) (STDOUT = Standard Output) is the default print function that always adds a newline. example of what it looks like internally: print("Your text here." + "\n") 
        g.define('CNLSTDOUT',  lambda *a: print(' '.join(gi_str(x) for x in a)) or None)
        g.define('STDOUT',   lambda *a: print(' '.join(gi_str(x) for x in a), end='') or None)
        g.define('STDIN',   lambda prompt='': input(gi_str(prompt)))
        g.define('STDIN_BUFFER',    lambda: sys.stdin.read())

        # ── system() ──────────────────────────────────────────────────────────
        # Concatenates all args as strings, runs as shell command
        g.define('system',  _gi_system)

        # ── type coercion ─────────────────────────────────────────────────────
        g.define('int',     lambda x: int(float(x)) if isinstance(x, str) else int(x))
        g.define('float',   lambda x: float(x))
        g.define('str',     lambda x: gi_str(x))
        g.define('bool',    lambda x: bool(x))
        g.define('typeof',  lambda x: self._typeof(x))

        # ── math ──────────────────────────────────────────────────────────────
        g.define('math', {
            'abs':    abs,
            'sqrt':   math.sqrt,
            'floor':  math.floor,
            'ceil':   math.ceil,
            'round':  round,
            'pi':     math.pi,
            'e':      math.e,
            'tau':    math.tau,
            'pow':    lambda x,y: x**y,
            'min':    lambda *a: min(*a),
            'max':    lambda *a: max(*a),
            'sin':    math.sin, 'cos':math.cos, 'tan':math.tan,
            'asin':   math.asin,'acos':math.acos,'atan':math.atan,
            'atan2':  math.atan2,
            'log':    math.log,'log2':math.log2,'log10':math.log10,
            'exp':    math.exp,
            'inf':    math.inf, 'nan': math.nan,
            'random': random.random,
            'randint':random.randint,
            'choice': random.choice,
            'shuffle':lambda lst: random.shuffle(lst) or lst,
        })

        # ── strings ───────────────────────────────────────────────────────────
        g.define('strlen',     lambda s: len(s))
        g.define('substr',     lambda s,a,b: s[a:b])
        g.define('split',      lambda s,d=' ': s.split(d))
        g.define('join',       lambda d,lst: d.join(gi_str(x) for x in lst))
        g.define('trim',       lambda s: s.strip())
        g.define('upper',      lambda s: s.upper())
        g.define('lower',      lambda s: s.lower())
        g.define('contains',   lambda s,sub: sub in s)
        g.define('replace',    lambda s,a,b: s.replace(a,b))
        g.define('startswith', lambda s,p: s.startswith(p))
        g.define('endswith',   lambda s,p: s.endswith(p))
        g.define('format',     lambda s,*a: s.format(*a))
        g.define('charcode',   lambda s: ord(s[0]) if s else 0)
        g.define('fromcode',   lambda n: chr(int(n)))
        g.define('chars',      lambda s: list(s))

        # ── collections ───────────────────────────────────────────────────────
        g.define('len',      lambda x: len(x))
        g.define('push',     lambda lst,v: lst.append(v) or None)
        g.define('pop',      lambda lst: lst.pop())
        g.define('insert',   lambda lst,i,v: lst.insert(i,v) or None)
        g.define('remove',   lambda lst,v: lst.remove(v) or None)
        g.define('reverse',  lambda lst: lst.reverse() or None)
        g.define('sort',     lambda lst: lst.sort() or None)
        g.define('slice',    lambda lst,a,b: lst[a:b])
        g.define('range',    lambda *a: list(range(*[int(x) for x in a])))
        g.define('keys',     lambda d: list(d.keys()))
        g.define('values',   lambda d: list(d.values()))
        g.define('items',    lambda d: [[k,v] for k,v in d.items()])
        g.define('haskey',   lambda d,k: k in d)
        g.define('delkey',   lambda d,k: d.pop(k, None))
        g.define('map',      lambda f,lst: [self._call_value(f,[x],0) for x in lst])
        g.define('filter',   lambda f,lst: [x for x in lst if self._call_value(f,[x],0)])
        g.define('reduce',   lambda f,lst,init=None: self._reduce(f,lst,init))
        g.define('zip',      lambda a,b: [list(p) for p in zip(a,b)])
        g.define('enumerate',lambda lst: [[i,v] for i,v in enumerate(lst)])
        g.define('sorted',   lambda lst,rev=False: sorted(lst, reverse=bool(rev)))
        g.define('any',      lambda lst: any(lst))
        g.define('all',      lambda lst: all(lst))
        g.define('sum',      lambda lst: sum(lst))

        # ── OS / filesystem ───────────────────────────────────────────────────
        g.define('exit',        lambda code=0: sys.exit(int(code)))
        g.define('args',        sys.argv[1:])
        g.define('getenv',      lambda k,d=None: os.environ.get(k, d))
        g.define('setenv',      lambda k,v: os.environ.__setitem__(k, v) or None)
        g.define('getcwd',      lambda: os.getcwd())
        g.define('chdir',       lambda p: os.chdir(p) or None)
        g.define('listdir',     lambda p='.': os.listdir(p))
        g.define('exists',      lambda p: os.path.exists(p))
        g.define('isfile',      lambda p: os.path.isfile(p))
        g.define('isdir',       lambda p: os.path.isdir(p))
        g.define('mkdir',       lambda p: os.makedirs(p, exist_ok=True) or None)
        g.define('remove_file', lambda p: os.remove(p) or None)
        g.define('rename',      lambda s,d: os.rename(s,d) or None)
        g.define('abspath',     lambda p: os.path.abspath(p))
        g.define('basename',    lambda p: os.path.basename(p))
        g.define('dirname',     lambda p: os.path.dirname(p))
        g.define('joinpath',    lambda *p: os.path.join(*[str(x) for x in p]))
        g.define('sleep',       lambda s: time.sleep(float(s)) or None)
        g.define('time',        lambda: time.time())
        g.define('clock',       lambda: time.perf_counter())
        g.define('popen',       lambda cmd: subprocess.check_output(
                                    cmd, shell=True, text=True, stderr=subprocess.STDOUT))

        # ── file I/O ──────────────────────────────────────────────────────────
        g.define('file', self._gi_open)

        # ── JSON ──────────────────────────────────────────────────────────────
        g.define('json', {
            'parse':     lambda s: json.loads(s),
            'stringify': lambda v,indent=None: json.dumps(v, indent=indent),
        })

        # ── native library loading ─────────────────────────────────────────────
        #   cbox.loadlib("kernel32")   or   loadlib("kernel32")
        g.define('cbox',    {'loadlib': _gi_loadlib})
        g.define('loadlib', _gi_loadlib)

        # ── assertions / errors ───────────────────────────────────────────────
        g.define('assert', lambda cond,msg="Assertion failed":
                 (_ for _ in ()).throw(RuntimeError_(msg)) if not cond else None)
        g.define('error',  lambda msg: (_ for _ in ()).throw(RuntimeError_(str(msg))))

    # ─────────────────────────────────────────────────────────────────────────
    def _gi_open(self, path, mode='r'):
        try:
            fh = open(path, mode, encoding='utf-8' if 'b' not in mode else None)
        except Exception as e:
            raise RuntimeError_(str(e))
        obj = {
            '__fh__':    fh,
            'read':      lambda *a: fh.read(*a),
            'readline':  lambda: fh.readline(),
            'readlines': lambda: fh.readlines(),
            'write':     lambda s: fh.write(gi_str(s)) or None,
            'close':     lambda: fh.close() or None,
            'name':      path,
        }
        return obj

    def _typeof(self, x):
        if x is None:               return 'null'
        if isinstance(x, bool):     return 'bool'
        if isinstance(x, (int,float)): return 'number'
        if isinstance(x, str):      return 'string'
        if isinstance(x, list):     return 'list'
        if isinstance(x, dict):     return 'dict'
        if isinstance(x, GIFunction):  return 'func'
        if isinstance(x, GIClass):     return 'class'
        if isinstance(x, GIInstance):  return x.klass.name
        if isinstance(x, GILib):       return 'lib'
        return 'unknown'

    def _reduce(self, f, lst, init):
        if not lst: return init
        acc = init if init is not None else lst[0]
        for x in (lst if init is not None else lst[1:]):
            acc = self._call_value(f, [acc, x], 0)
        return acc

    # ─────────────────────────────────────────────────────────────────────────
    def run(self, node, env=None):
        if env is None: env = self.globals
        return self.exec_block(node, env)

    def exec_block(self, block, env):
        if not isinstance(block, Block):
            raise ReturnSignal(self.eval_expr(block, env))
        for stmt in block.stmts:
            self.exec_stmt(stmt, env)

    def exec_stmt(self, node, env):
        if isinstance(node, LetStmt):
            env.define(node.name, self.eval_expr(node.value, env))

        elif isinstance(node, SetStmt):
            env.update(node.target, self.eval_expr(node.value, env), node.line)

        elif isinstance(node, AssignStmt):
            val = self.eval_expr(node.value, env)
            if node.op != '=':
                cur = env.get(node.target, node.line)
                if   node.op == '+=': val = self._add(cur, val)
                elif node.op == '-=': val = cur - val
                elif node.op == '*=': val = cur * val
                elif node.op == '/=': val = cur / val
            env.set(node.target, val)

        elif isinstance(node, SetAttr):
            obj = self.eval_expr(node.obj, env)
            val = self.eval_expr(node.value, env)
            if isinstance(obj, GIInstance): obj.set(node.attr, val)
            elif isinstance(obj, dict):     obj[node.attr] = val
            else: raise RuntimeError_(f"Cannot set attribute on {self._typeof(obj)}")

        elif isinstance(node, SetIndex):
            obj = self.eval_expr(node.obj, env)
            idx = self.eval_expr(node.idx, env)
            obj[idx] = self.eval_expr(node.value, env)

        elif isinstance(node, IfStmt):
            for cond, body in node.branches:
                if self.eval_expr(cond, env):
                    self.exec_block(body, Env(env)); return
            if node.else_block:
                self.exec_block(node.else_block, Env(env))

        elif isinstance(node, WhileStmt):
            while self.eval_expr(node.cond, env):
                try:   self.exec_block(node.body, Env(env))
                except ContinueSignal: continue
                except BreakSignal:    break

        elif isinstance(node, ForStmt):
            iterable = self.eval_expr(node.iterable, env)
            if isinstance(iterable, dict): iterable = list(iterable.keys())
            for item in iterable:
                inner = Env(env); inner.define(node.var, item)
                try:   self.exec_block(node.body, inner)
                except ContinueSignal: continue
                except BreakSignal:    break

        elif isinstance(node, FuncDef):
            env.define(node.name, GIFunction(node.name, node.params, node.body, env))

        elif isinstance(node, ReturnStmt):
            raise ReturnSignal(self.eval_expr(node.value, env) if node.value else None)

        elif isinstance(node, PassStmt):     pass
        elif isinstance(node, ContinueStmt): raise ContinueSignal()
        elif isinstance(node, BreakStmt):    raise BreakSignal()

        elif isinstance(node, WithStmt):
            ctx = self.eval_expr(node.call, env)
            inner = Env(env); inner.define(node.alias, ctx)
            try:
                self.exec_block(node.body, inner)
            finally:
                close = None
                if isinstance(ctx, dict) and 'close' in ctx:
                    close = ctx['close']
                elif isinstance(ctx, GIInstance):
                    try: close = ctx.get('close')
                    except: pass
                if callable(close): close()

        elif isinstance(node, ClassDef):
            base = env.get(node.base) if node.base else None
            methods = {}; cls_env = Env(env)
            for stmt in node.body.stmts:
                if isinstance(stmt, FuncDef):
                    methods[stmt.name] = GIFunction(stmt.name, stmt.params, stmt.body, cls_env)
            env.define(node.name, GIClass(node.name, base, methods, cls_env))

        elif isinstance(node, ImportStmt):
            self._do_import(node, env)

        elif isinstance(node, ExprStmt):
            self.eval_expr(node.expr, env)

    # ─────────────────────────────────────────────────────────────────────────
    #  IMPORT
    # ─────────────────────────────────────────────────────────────────────────
    def _do_import(self, node: ImportStmt, env: Env):
        path   = node.path
        alias  = node.alias
        is_pkg = node.is_pkg

        file_path = _resolve_import(path, is_pkg, self.script_dir)

        if file_path is None:
            # Fall back to Python stdlib
            import importlib
            try:
                py_mod = importlib.import_module(path.replace('/', '.'))
                parts  = [p for p in re.split(r'[./\\]+', path) if p]
                aname  = alias or parts[-1]
                env.define(aname, py_mod)
                return
            except ImportError:
                pass
            raise RuntimeError_(
                f"Cannot find module '{path}'.\n"
                f"  Searched: {_LOCAL_PKG}  and  {_HOME_PKG}\n"
                f"  Install with:  python3 gi.py --install <git-url>"
            )

        if file_path in self._mod_cache:
            exported = self._mod_cache[file_path]
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                src = f.read()
            mod_dir    = os.path.dirname(file_path)
            mod_interp = Interpreter(script_dir=mod_dir)
            mod_env    = Env(mod_interp.globals)
            try:
                toks = Lexer(src).tokenize()
                ast  = Parser(toks).parse()
                mod_interp.exec_block(ast, mod_env)
            except ReturnSignal:
                pass
            exported = dict(mod_env.vars)
            self._mod_cache[file_path] = exported

        parts  = [p for p in re.split(r'[./\\]+', path) if p]
        aname  = alias or parts[-1]
        env.define(aname, exported)

    # ─────────────────────────────────────────────────────────────────────────
    #  EXPRESSIONS
    # ─────────────────────────────────────────────────────────────────────────
    def eval_expr(self, node, env):
        if isinstance(node, NumberLit): return node.v
        if isinstance(node, StringLit): return node.v
        if isinstance(node, BoolLit):   return node.v
        if isinstance(node, NullLit):   return None
        if isinstance(node, ListLit):
            return [self.eval_expr(i, env) for i in node.items]
        if isinstance(node, DictLit):
            d = {}
            for k,v in node.pairs: d[self.eval_expr(k,env)] = self.eval_expr(v,env)
            return d
        if isinstance(node, Ident):
            return env.get(node.name, node.line)
        if isinstance(node, BinOp):
            return self.eval_binop(node, env)
        if isinstance(node, UnaryOp):
            v = self.eval_expr(node.expr, env)
            if node.op == '-':         return -v
            if node.op in ('!','not'): return not v
        if isinstance(node, Call):
            callee = self.eval_expr(node.callee, env)
            args   = [self.eval_expr(a, env) for a in node.args]
            return self._call_value(callee, args, node.line)
        if isinstance(node, GetAttr):
            return self._get_attr(self.eval_expr(node.obj, env), node.attr, node.line)
        if isinstance(node, Index):
            obj = self.eval_expr(node.obj, env)
            idx = self.eval_expr(node.idx, env)
            try: return obj[idx]
            except (KeyError,IndexError) as e: raise RuntimeError_(str(e))
        if isinstance(node, NewExpr):
            klass = env.get(node.cls, node.line)
            return self._instantiate(klass, [self.eval_expr(a,env) for a in node.args], node.line)
        if isinstance(node, LambdaExpr):
            return GIFunction('<lambda>', node.params, node.body, env)
        raise RuntimeError_(f"Unknown expr node: {type(node).__name__}")

    def _get_attr(self, obj, attr, line):
        if isinstance(obj, GIInstance): return obj.get(attr)

        if isinstance(obj, dict):
            if attr in obj: return obj[attr]
            raise RuntimeError_(f"No key '{attr}' in dict/module at line {line}")

        if isinstance(obj, GILib):
            try:
                cfn = getattr(obj.lib, attr)
            except AttributeError:
                raise RuntimeError_(f"Library '{obj.name}' has no symbol '{attr}'")
            def _caller(*args):
                c_args = []
                for a in args:
                    if isinstance(a, int):    c_args.append(ctypes.c_long(a))
                    elif isinstance(a, float): c_args.append(ctypes.c_double(a))
                    elif isinstance(a, str):   c_args.append(ctypes.c_char_p(a.encode()))
                    else: c_args.append(a)
                return cfn(*c_args)
            return _caller

        if isinstance(obj, list):
            methods = {
                'push':     lambda v: obj.append(v) or None,
                'pop':      lambda: obj.pop(),
                'len':      lambda: len(obj),
                'sort':     lambda: obj.sort() or None,
                'reverse':  lambda: obj.reverse() or None,
                'slice':    lambda a,b=None: obj[a:b],
                'join':     lambda d='': d.join(gi_str(x) for x in obj),
                'map':      lambda f: [self._call_value(f,[x],line) for x in obj],
                'filter':   lambda f: [x for x in obj if self._call_value(f,[x],line)],
                'contains': lambda v: v in obj,
                'index':    lambda v: obj.index(v),
                'insert':   lambda i,v: obj.insert(i,v) or None,
            }
            if attr in methods: return methods[attr]

        if isinstance(obj, str):
            methods = {
                'len':        lambda: len(obj),
                'upper':      lambda: obj.upper(),
                'lower':      lambda: obj.lower(),
                'trim':       lambda: obj.strip(),
                'split':      lambda d=' ': obj.split(d),
                'replace':    lambda a,b: obj.replace(a,b),
                'contains':   lambda s: s in obj,
                'startswith': lambda p: obj.startswith(p),
                'endswith':   lambda p: obj.endswith(p),
                'find':       lambda s: obj.find(s),
                'format':     lambda *a: obj.format(*a),
                'chars':      lambda: list(obj),
                'strip':      lambda: obj.strip(),
            }
            if attr in methods: return methods[attr]

        if hasattr(obj, attr): return getattr(obj, attr)
        raise RuntimeError_(f"No attribute '{attr}' on {self._typeof(obj)!r} at line {line}")

    def _call_value(self, callee, args, line):
        if callable(callee):
            try:   return callee(*args)
            except RuntimeError_ as e: raise
            except Exception as e:
                raise RuntimeError_(f"{e} (line {line})")

        if isinstance(callee, GIFunction):
            fn_env = Env(callee.closure)
            for i,p in enumerate(callee.params):
                fn_env.define(p, args[i] if i < len(args) else None)
            try:   self.exec_block(callee.body, fn_env)
            except ReturnSignal as r: return r.val
            return None

        if isinstance(callee, BoundMethod):
            fn_env = Env(callee.func.closure)
            fn_env.define('self', callee.instance)
            for i,p in enumerate(callee.func.params[1:]):
                fn_env.define(p, args[i] if i < len(args) else None)
            try:   self.exec_block(callee.func.body, fn_env)
            except ReturnSignal as r: return r.val
            return None

        if isinstance(callee, GIClass):
            return self._instantiate(callee, args, line)

        raise RuntimeError_(f"'{self._typeof(callee)}' is not callable at line {line}")

    def _instantiate(self, klass, args, line):
        inst = GIInstance(klass)
        k = klass
        while k:
            if 'init' in k.methods:
                fn_env = Env(k.methods['init'].closure)
                fn_env.define('self', inst)
                for i,p in enumerate(k.methods['init'].params[1:]):
                    fn_env.define(p, args[i] if i < len(args) else None)
                try:   self.exec_block(k.methods['init'].body, fn_env)
                except ReturnSignal: pass
                break
            k = k.base
        return inst

    def _add(self, a, b):
        if isinstance(a, list) and isinstance(b, list): return a + b
        if isinstance(a, list): return a + [b]
        if isinstance(a, str) or isinstance(b, str): return gi_str(a) + gi_str(b)
        return a + b

    def eval_binop(self, node, env):
        op = node.op
        if op == '&&':
            return bool(self.eval_expr(node.left,env)) and bool(self.eval_expr(node.right,env))
        if op == '||':
            return bool(self.eval_expr(node.left,env)) or bool(self.eval_expr(node.right,env))
        l = self.eval_expr(node.left, env)
        r = self.eval_expr(node.right, env)
        try:
            if op == '+':  return self._add(l, r)
            if op == '-':  return l - r
            if op == '*':
                if isinstance(l, str) and isinstance(r, (int,float)): return l * int(r)
                return l * r
            if op == '/':
                if r == 0: raise RuntimeError_("Division by zero")
                return l / r
            if op == '%':  return l % r
            if op == '**': return l ** r
            if op == '==': return l == r
            if op == '!=': return l != r
            if op == '<':  return l < r
            if op == '>':  return l > r
            if op == '<=': return l <= r
            if op == '>=': return l >= r
        except RuntimeError_: raise
        except ZeroDivisionError: raise RuntimeError_("Division by zero")
        except TypeError as e:   raise RuntimeError_(f"Type error in '{op}': {e}")

# ═════════════════════════════════════════════════════════════════════════════
#  PACKAGE INSTALLER   python3 gi.py --install <git-url>
# ═════════════════════════════════════════════════════════════════════════════
def cmd_install(target: str):
    """
    Clone (or pull) a GI package from a git URL into ~/.glang/packages/.

    The package name = last segment of the URL (without .git).
    A glang.json  { "name": "g" }  in the repo root overrides the name.

    After install, use:   import <"g.module">
    """
    os.makedirs(_HOME_PKG, exist_ok=True)

    if not shutil.which('git'):
        print("\033[91m[glang] git not found in PATH.\033[0m"); sys.exit(1)

    raw_name = target.rstrip('/').split('/')[-1]
    if raw_name.endswith('.git'): raw_name = raw_name[:-4]
    dest = os.path.join(_HOME_PKG, raw_name)

    if os.path.isdir(dest):
        print(f"\033[93m[glang] Updating '{raw_name}' ...\033[0m")
        result = subprocess.run(['git', '-C', dest, 'pull'])
    else:
        print(f"\033[96m[glang] Installing '{raw_name}' from {target} ...\033[0m")
        result = subprocess.run(['git', 'clone', '--depth=1', target, dest])

    if result.returncode != 0:
        print(f"\033[91m[glang] Failed (exit {result.returncode}).\033[0m")
        sys.exit(result.returncode)

    manifest = os.path.join(dest, 'glang.json')
    if os.path.isfile(manifest):
        try:
            with open(manifest) as f: meta = json.load(f)
            declared = meta.get('name', raw_name)
            if declared != raw_name:
                new_dest = os.path.join(_HOME_PKG, declared)
                if os.path.exists(new_dest): shutil.rmtree(new_dest)
                os.rename(dest, new_dest); dest = new_dest; raw_name = declared
        except Exception as e:
            print(f"\033[93m[glang] Warning: glang.json unreadable: {e}\033[0m")

    print(f"\033[92m[glang] '{raw_name}' installed → {dest}\033[0m")
    print(f'\033[90m        Use:  import <"{raw_name}.module">\033[0m')

# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINTS
# ═════════════════════════════════════════════════════════════════════════════
def run_source(src: str, filename: str = '<input>'):
    script_dir = os.path.dirname(os.path.abspath(filename)) if filename != '<input>' else os.getcwd()
    try:
        tokens = Lexer(src).tokenize()
        ast    = Parser(tokens).parse()
        interp = Interpreter(script_dir=script_dir)
        interp.run(ast)
    except (LexError, ParseError) as e:
        print(f"\033[91m[GI Syntax Error] {e}\033[0m", file=sys.stderr); sys.exit(1)
    except RuntimeError_ as e:
        print(f"\033[91m[GI Runtime Error] {e}\033[0m", file=sys.stderr); sys.exit(1)
    except SystemExit: raise
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)

def repl():
    BANNER = """\033[96m
  ██████╗ ██╗
 ██╔════╝ ██║
 ██║  ███╗██║
 ██║   ██║██║
 ╚██████╔╝████████╗
  ╚═════╝ ╚═══════╝   G Language Interpreted v0.2
\033[0m\033[90mType exit() or Ctrl+C to quit.\033[0m\n"""
    print(BANNER)
    interp = Interpreter(script_dir=os.getcwd())
    buf = []; depth = 0
    while True:
        try:
            line = input(f"\033[96m{'g> ' if depth==0 else '... '}\033[0m")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!"); break
        if not line.strip() and depth == 0: continue
        buf.append(line); depth += line.count('{') - line.count('}')
        if depth <= 0:
            src = '\n'.join(buf); buf = []; depth = 0
            try:
                tokens = Lexer(src).tokenize()
                ast    = Parser(tokens).parse()
                if len(ast.stmts) == 1 and isinstance(ast.stmts[0], ExprStmt):
                    try:
                        val = interp.eval_expr(ast.stmts[0].expr, interp.globals)
                        if val is not None: print(f"\033[93m=> {gi_str(val)}\033[0m")
                    except RuntimeError_ as e: print(f"\033[91m[Error] {e}\033[0m")
                else:
                    try:   interp.run(ast, interp.globals)
                    except RuntimeError_ as e: print(f"\033[91m[Error] {e}\033[0m")
            except (LexError, ParseError) as e:
                print(f"\033[91m[Syntax] {e}\033[0m")

def main():
    args = sys.argv[1:]

    if args and args[0] == '--install':
        if len(args) < 2:
            print("Usage: python3 gi.py --install <git-url or local-path>"); sys.exit(1)
        cmd_install(args[1]); return

    if args:
        path = args[0]
        if not path.endswith('.g'):
            print(f"Warning: expected .g file, got '{path}'", file=sys.stderr)
        sys.argv = args
        with open(path, 'r', encoding='utf-8') as f: src = f.read()
        run_source(src, path); return

    repl()

if __name__ == '__main__':
    main()