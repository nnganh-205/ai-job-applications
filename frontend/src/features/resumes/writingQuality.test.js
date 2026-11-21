import {test,expect} from 'bun:test';
import {writingQuality,quickEditorialEdits} from './writingQuality.js';
test('empty entry has no fabricated quality score',()=>{const q=writingQuality({});expect(q.score).toBe(0);expect(q.checks.every(c=>c.status==='empty')).toBe(true);});
test('diagnostics point to the actual affected bullet',()=>{const q=writingQuality({description:['mình làm giao diện','Hỗ trợ kiểm thử bằng React.']});expect(q.checks.find(c=>c.id==='pronoun').bad).toEqual([1]);expect(q.checks.find(c=>c.id==='punctuation').bad).toEqual([1]);});
test('a factual qualitative bullet can pass without invented metrics',()=>{const q=writingQuality({description:['Hỗ trợ xây dựng giao diện bằng React.']});expect(q.score).toBe(100);expect(q.hasMetric).toBe(false);});
test('quick fixes preserve quantities, technology and contribution',()=>{const e={description:['mình hỗ trợ kiểm thử 20 API bằng Python']};const p=quickEditorialEdits(e,'pronoun')[0];expect(p.proposed).toEqual(['Hỗ trợ kiểm thử 20 API bằng Python']);expect(e.description[0]).toStartWith('mình');const punctuation=quickEditorialEdits(e,'punctuation')[0];expect(punctuation.proposed[0]).toBe('Mình hỗ trợ kiểm thử 20 API bằng Python.');});
test('quick fixes never guess specifics for vague claims',()=>{expect(quickEditorialEdits({description:['mình làm nhiều thứ']},'specific')).toEqual([]);});
test('missing punctuation deducts only five points for the whole entry',()=>{
  const q=writingQuality({description:['Hỗ trợ kiểm thử API bằng Python','Phân tích dữ liệu bằng SQL']});
  expect(q.checks.find(c=>c.id==='punctuation').bad).toEqual([1,2]);
  expect(q.score).toBe(95);
});
test('punctuation deduction remains five alongside another issue',()=>{
  const complete=writingQuality({description:['Tôi hỗ trợ kiểm thử API bằng Python.']});
  const missing=writingQuality({description:['Tôi hỗ trợ kiểm thử API bằng Python']});
  expect(complete.score).toBe(80);
  expect(missing.score).toBe(75);
});
test('Vietnamese bullets allow sixty whitespace units while English stays at thirty-eight',()=>{
  const check=(text)=>writingQuality({description:[text]}).checks.find(c=>c.id==='length').status;
  expect(check('Triển '+Array(59).fill('khai').join(' ')+'.')).toBe('pass');
  expect(check('Triển '+Array(60).fill('khai').join(' ')+'.')).toBe('warning');
  expect(check('Built '+Array(38).fill('tools').join(' ')+'.')).toBe('warning');
});
