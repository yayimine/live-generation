import copy
import unittest
from protocol import messages, validate_review

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.good = {'rating':7,'feedback':'Plan the return route.', 'nextLevel':{
            'title':'Corners','description':'Collect two corner goals.','seconds':35,
            'goals':[{'x':-5,'y':3},{'x':5,'y':-3}]}}
    def test_valid(self):
        self.assertEqual(validate_review(self.good)['rating'], 7)
    def test_reject_geometry(self):
        for point in ({'x':9,'y':0},{'x':0,'y':0},{'x':float('nan'),'y':2}):
            bad=copy.deepcopy(self.good); bad['nextLevel']['goals']=[point]
            with self.assertRaises(ValueError): validate_review(bad)
    def test_overlap(self):
        self.good['nextLevel']['goals'] *= 2
        with self.assertRaises(ValueError): validate_review(self.good)
    def test_bad_rating(self):
        for value in (0,11,True,7.5):
            self.good['rating']=value
            with self.assertRaises(ValueError): validate_review(self.good)
    def test_preserves_all_events(self):
        run={'inputs':[{'time':i/20,'mask':i%16} for i in range(1000)],'hits':[{'time':12,'goal':0}]}
        import json
        self.assertEqual(json.loads(messages(run)[1]['content']), run)

if __name__ == '__main__': unittest.main()
