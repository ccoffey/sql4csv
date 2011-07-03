from pyparsing import *
import csv

class sql4csv(object):
    """An SQL like interface for .csv files"""    
    def __init__(self, filename, fieldnames = None, fieldtypes = {}, delimiter=','):
        self.filename = filename
        self.fieldnames = fieldnames
        self.fieldtypes = fieldtypes
        self.delimiter = delimiter
        
        #Keywords
        keyword_as = Keyword('as', caseless=True)
        keyword_select = Keyword('select', caseless=True)
        keyword_where = Keyword('where', caseless=True)
        
        # Grammar definition
        anumExpr = Combine(Word(alphanums) + Optional(OneOrMore(OneOrMore(oneOf("_ -")) + Word(alphanums))))
        field = Literal('$') + anumExpr('field_name')
        as_field = Literal('$') + anumExpr('new_field_name')
            
        where_field = field.copy()
        where_field.setParseAction(lambda f: self.parse_field_as(f, True))

        field_as = field + Optional(keyword_as + as_field)
        field_as_in_function = field_as.copy()
        
        field_as.setParseAction(lambda f: self.parse_field_as(f, False))
        field_as_in_function.setParseAction(lambda f: self.parse_field_as(f, True))

        E = CaselessLiteral("E")
        binop = oneOf("== = != < > >= <= eq ne lt le gt ge", caseless=True)
        binop.setParseAction(lambda bo: self.parseBinaryOp(bo))
        
        arithSign = Word("+-",exact=1)
        realNum = Combine( Optional(arithSign) + ( Word( nums ) + "." + Optional( Word(nums) ) | ( "." + Word(nums) ) ) + Optional(E + Optional(arithSign) + Word(nums)))
        realNum.setParseAction(lambda n: float(n[0]))        
        intNum = Combine( Optional(arithSign) + Word( nums ) + Optional( E + Optional("+") + Word(nums) ) )
        intNum.setParseAction(lambda n: int(n[0]))
        
        fun = Forward()
        function = '#' + Word(nums) + Group(Literal('(') + Optional(delimitedList(Group(realNum | intNum | quotedString | field_as_in_function | fun))) + Literal(')')) + Optional(keyword_as + field)
        function.setParseAction(lambda f: self.parse_function(f))
        fun << function

        where_fun = Forward()
        where_function = '#' + Word(nums) + Group(Literal('(') + Optional(delimitedList(Group(realNum | intNum | quotedString | where_field | where_fun))) + Literal(')'))
        where_function.setParseAction(lambda f: self.parse_function(f))
        where_fun << where_function

        star = Literal('*')
        star.setParseAction(lambda: self.parse_star())
        
        whereExpression = Forward()
        and_ = Keyword("and", caseless=True)
        or_ = Keyword("or", caseless=True)
        
        columnRval = realNum | intNum | quotedString | where_field | where_function 
        whereCondition = Group((columnRval + binop + columnRval).setParseAction(lambda c: self.parseCondition(c)) | ( "(" + whereExpression + ")" ))
        whereExpression << whereCondition + ZeroOrMore( ( and_ | or_ ).setParseAction(lambda c: self.parseAndOr(c)) + whereExpression )

        self.grammar = keyword_select + delimitedList(star | field_as | function) + Optional(keyword_where + whereExpression)
        self.row_in = {}
        self.row_out = {}
        self.conditions = ''
    
    #Function for parsing binary operators.
    def parseBinaryOp(self, bo):
        bo = bo[0].lower()
        if bo in ('=', 'eq'):
            bo = '=='
        elif bo == 'ne':
            bo = '!='
        elif bo == 'lt':
            bo = '<'
        elif bo == 'gt':
            bo = '>'
        elif bo == 'le':
            bo = '<='
        elif bo == 'ge':
            bo = '>='
        return bo
    
    def parseAndOr(self, c):
        self.conditions = '%s %s' % (self.conditions, c[0])
        return
    
    def parseCondition(self, tokens):
        # The tokens are of the following form
        # tokens[0][0] = value
        # tokens[0][1] = binary operator
        # tokens[0][2] = value
        lvalue = tokens[0]
        binary_operator = tokens[1]
        rvalue = tokens[2]
        
        b = eval('lvalue %s rvalue' % binary_operator)
        self.conditions = '%s %s' % (self.conditions, b) 
        
        return
    
    # Function for parsing a star.
    def parse_star(self):
        for key in self.row_in.keys():
            self.row_out[key] = self.row_in[key]
        return self.row_in

    # Function for parsing a function.
    def parse_function(self, tokens):
        # The tokens are of the following form
        # tokens[0] = '#'
        # tokens[1] = function_index
        # tokens[2] = (parameters)
        # tokens[3] = 'as'
        # tokens[4] = '$'
        # tokens[5] = field

        function_index = int(tokens[1])
        
        params = []
        for param in tokens[2][1:-1]:
            params.append(param[0])
        
        fun = self.funs[function_index]
        
        if len(tokens) == 6:    
            key = tokens[5]    
            self.row_out[key] = fun(*params)
            return self.row_out[key]
        else:
            return fun(*params)
    
    def parse_field_as(self, tokens, inside_function=False):
        key = tokens['field_name']
        
        #A field can be in the input row or output row. 
        if key in self.row_in:
            row = self.row_in[key]
        
        elif key in self.row_out:
            row = self.row_out[key]

        else:
            raise('Key Error: %s' % key)
        
        #If we know the type of this field, convert it.
        if key in self.fieldtypes:                    
            row = self.fieldtypes[key](row)
        
        if 'new_field_name' in tokens:
            new_key = tokens['new_field_name']
            self.row_out[new_key] = row
        else:
            #If we are inside a function, then this field is a parameter and should not be included in the output row.
            if not inside_function:
                self.row_out[key] = row
    
        return row
    
    # Execute a query on a csv file and return the results immediately.
    def query(self, query_str, funs = []):
        self.funs = funs
        output = []
                
        self.input = csv.DictReader(open(self.filename), fieldnames=self.fieldnames, delimiter=self.delimiter)

        for self.row_in in self.input:
            self.row_out = {}
            self.conditions = ''
            self.grammar.parseString(query_str, True)
            
            if not self.row_out == {} and (self.conditions == '' or eval(self.conditions)):
                output.append(self.row_out)
        return output
    
    # Execute a query on a csv file and return the results as an iterable.
    def lazy_query(self, query_str, funs = []):
        self.funs = funs
                
        self.input = csv.DictReader(open(self.filename), fieldnames=self.fieldnames, delimiter=self.delimiter)

        for self.row_in in self.input:
            self.row_out = {}
            self.conditions = ''
            self.grammar.parseString(query_str, True)
            
            if not self.row_out == {} and (self.conditions == '' or eval(self.conditions)):
                yield self.row_out
    
    @staticmethod
    def join(table0, table1, join_query):
        return 'joined'
    
if __name__ == '__main__':
    # Test the join function
    ds_persons = sql4csv('persons.csv', fieldtypes={'P_Id': int})
    ds_orders = sql4csv('orders.csv', fieldtypes={'O_Id': int})

    ds_joined = sql4csv.join(ds_persons, ds_orders, '0.P_Id == 1.O_Id')

    # Test the examples from the GitHub Wiki and make sure they return the expected results.
    ds_0 = sql4csv('ds_0.csv')
    
    print 'Running tests...'

    result = str(ds_0.query('select $fname, $lname'))
    actual = "[{'lname': 'coffey', 'fname': 'cathal'}, {'lname': 'smith', 'fname': 'joe'}, {'lname': 'burne', 'fname': 'mary'}]"
    print "Test 0: %s" % (result == actual)
    
    result = str(ds_0.query('select $fname as $first_name, $lname as $last_name'))
    actual = "[{'first_name': 'cathal', 'last_name': 'coffey'}, {'first_name': 'joe', 'last_name': 'smith'}, {'first_name': 'mary', 'last_name': 'burne'}]"
    print "Test 1: %s" % (result == actual)
    
    result = str(ds_0.query('select #0($fname, $lname) as $fullname', [lambda a, b: '%s %s' % (a, b)]))
    actual = "[{'fullname': 'cathal coffey'}, {'fullname': 'joe smith'}, {'fullname': 'mary burne'}]"
    print "Test 2: %s" % (result == actual)
    
    result = str(ds_0.query('select $fname, $lname, #0($fname, $lname) as $fullname', [lambda a, b: '%s %s' % (a, b)]))
    actual = "[{'lname': 'coffey', 'fullname': 'cathal coffey', 'fname': 'cathal'}, {'lname': 'smith', 'fullname': 'joe smith', 'fname': 'joe'}, {'lname': 'burne', 'fullname': 'mary burne', 'fname': 'mary'}]"
    print "Test 3: %s" % (result == actual)
    
    result = str(ds_0.query('select #0($fname as $fname, $lname as $lname) as $fullname', [lambda a, b: '%s %s' % (a, b)]))
    actual = "[{'lname': 'coffey', 'fullname': 'cathal coffey', 'fname': 'cathal'}, {'lname': 'smith', 'fullname': 'joe smith', 'fname': 'joe'}, {'lname': 'burne', 'fullname': 'mary burne', 'fname': 'mary'}]"
    print "Test 4: %s" % (result == actual)
    
    result = str(ds_0.query('select #0($age, $fav_num) as $result', [lambda a, b: a + b]))
    actual = "[{'result': '213.1415'}, {'result': '315'}, {'result': '212.7182'}]"
    print "Test 5: %s" % (result == actual)
    
    ds_0 = sql4csv('ds_0.csv', fieldtypes={'age': int, 'fav_num': float})
    
    result = str(ds_0.query('select #0($age, $fav_num) as $result', [lambda a, b: a + b]))
    actual = "[{'result': 24.1415}, {'result': 36.0}, {'result': 23.7182}]"
    print "Test 6: %s" % (result == actual)
    
    result = str(ds_0.query('select * where $age = 21'))
    actual = "[{'lname': 'coffey', 'gender': 'male', 'age': '21', 'fav_num': '3.1415', 'fname': 'cathal'}, {'lname': 'burne', 'gender': 'female', 'age': '21', 'fav_num': '2.7182', 'fname': 'mary'}]"
    print "Test 7: %s" % (result == actual)
    
    result = str(ds_0.query('select * where $age = #0()', [lambda: 21]))
    actual = "[{'lname': 'coffey', 'gender': 'male', 'age': '21', 'fav_num': '3.1415', 'fname': 'cathal'}, {'lname': 'burne', 'gender': 'female', 'age': '21', 'fav_num': '2.7182', 'fname': 'mary'}]"
    print "Test 8: %s" % (result == actual)
    
    result = str(ds_0.query('select * where $age = #0(#1(), #2())', [lambda x, y: x  * y, lambda: 7, lambda: 3]))
    actual = "[{'lname': 'coffey', 'gender': 'male', 'age': '21', 'fav_num': '3.1415', 'fname': 'cathal'}, {'lname': 'burne', 'gender': 'female', 'age': '21', 'fav_num': '2.7182', 'fname': 'mary'}]"
    print "Test 9: %s" % (result == actual)
    
    result = str(ds_0.query('select * where ($age = 21) or ($age = 23) and $fav_num > 2'))
    actual = "[{'lname': 'coffey', 'gender': 'male', 'age': '21', 'fav_num': '3.1415', 'fname': 'cathal'}, {'lname': 'burne', 'gender': 'female', 'age': '21', 'fav_num': '2.7182', 'fname': 'mary'}]"
    print "Test 10: %s" % (result == actual)
    

