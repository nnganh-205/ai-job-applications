import {test,expect} from 'bun:test';
import {writingQuality,quickEditorialEdits} from './writingQuality.js';
test('empty entry has no fabricated quality score',()=>{const q=writingQuality({});expect(q.score).toBe(0);expect(q.checks.every(c=>c.status==='empty')).toBe(true);});
test('diagnostics point to the actual affected bullet',()=>{const q=writingQuality({description:['mình làm giao diện','Hỗ trợ kiểm thử bằng React.']});expect(q.checks.find(c=>c.id==='pronoun').bad).toEqual([1]);expect(q.checks.find(c=>c.id==='punctuation').bad).toEqual([1]);});
test('a factual qualitative bullet can pass without invented metrics',()=>{const q=writingQuality({description:['Hỗ trợ xây dựng giao diện bằng React.']});expect(q.score).toBe(100);expect(q.hasMetric).toBe(false);});
test('quick fixes preserve quantities, technology and contribution',()=>{const e={description:['mình hỗ trợ kiểm thử 20 API bằng Python']};const p=quickEditorialEdits(e,'pronoun')[0];expect(p.proposed).toEqual(['Hỗ trợ kiểm thử 20 API bằng Python']);expect(e.description[0]).toStartWith('mình');const punctuation=quickEditorialEdits(e,'punctuation')[0];expect(punctuation.proposed[0]).toBe('Mình hỗ trợ kiểm thử 20 API bằng Python.');});
test('quick fixes never guess specifics for vague claims',()=>{expect(quickEditorialEdits({description:['mình làm nhiều thứ']},'specific')).toEqual([]);});
